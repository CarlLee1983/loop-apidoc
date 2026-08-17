from __future__ import annotations

import hashlib
import heapq
import json
import os
import re
import stat
from collections.abc import Callable, Iterator
from pathlib import Path

from loop_apidoc.manifest.models import Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.privacy import (
    CONTACT_PII,
    CREDENTIAL_REFERENCE,
    PII_VALUE,
    SECRET_MATERIAL,
    TEST_PAYMENT_CARDS,
    iter_payment_card_numbers,
)
from loop_apidoc.source_risk.models import (
    RiskCoverageStatus,
    RiskSeverity,
    RiskVerdict,
    SourceRiskCoverage,
    SourceRiskFinding,
    SourceRiskReport,
)

SCHEMA_VERSION = "1"
RULESET_VERSION = "4"
MAX_REPORTED_FINDINGS = 1_000
_TRUNCATION_RULE_ID = "SR-FINDINGS-TRUNCATED"
#: Warning 的獨立額度。上限是全體來源共用的,而 leak 類規則(聯絡信箱、
#: 憑證引用、電話)在一份合格的大型文件裡是高頻的 —— 沒有這道分隔,
#: 「警告很多」會經由截斷 blocker 變成「拒絕」,而報告裡沒有任何一筆
#: 實質命中。Blocker 仍可用滿整個上限,所以警告永遠擠不掉真正的命中。
MAX_REPORTED_WARNINGS = 500
_WARNING_TRUNCATION_RULE_ID = "SR-WARNINGS-TRUNCATED"

_SCANNABLE_FORMATS = {
    SourceFormat.MARKDOWN,
    SourceFormat.HTML,
    SourceFormat.OPENAPI_JSON,
    SourceFormat.OPENAPI_YAML,
}
_UNICODE_TAG = re.compile("[\U000e0000-\U000e007f]")
_BIDI_OVERRIDE = re.compile("[\u202d\u202e]")
_CONTROL_CHARACTER = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_BIDI_FORMATTING = re.compile("[\u202a-\u202c\u2066-\u2069]")
_ZERO_WIDTH_FORMATTING = re.compile("[\u200b-\u200d\u2060\ufeff]")
_INSTRUCTION_OVERRIDE_TEXT = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions",
    re.IGNORECASE,
)
_CONTROL_TOKEN_TEXT = re.compile(
    r"<\|(?:system|assistant|tool|user)\|>"
    r"|</?(?:system|assistant|tool|user)(?:\s[^>]*)?>",
    re.IGNORECASE,
)

#: 一條規則就是一個「掃出命中起點」的函式。回傳位移而非 `re.Match`,因為
#: 卡號的命中未必等於樣式的命中 —— 它在候選內部,沒有對應的 match 物件。
_RuleScanner = Callable[[str], Iterator[int]]


def _is_not_leading_bom(match: re.Match[str]) -> bool:
    """Accept every zero-width formatting hit except a file-leading BOM.

    開頭的 BOM 是編碼副產物,不是有人藏字。純外觀,與內容無關。
    """
    return not (match.start() == 0 and match.group() == "\ufeff")


def _pattern_scanner(
    pattern: re.Pattern[str],
    accept: Callable[[re.Match[str]], bool] | None = None,
) -> _RuleScanner:
    def scan(text: str) -> Iterator[int]:
        for match in pattern.finditer(text):
            if accept is None or accept(match):
                yield match.start()

    return scan


def _payment_card_scanner(text: str) -> Iterator[int]:
    """Locate card numbers, not card candidates.

    候選只是「長度合格的數字串」,判準是 Luhn 加上卡組織公告的測試卡號 ——
    後者出現在付款文件裡是必要內容,報它等於對每一份付款文件產生一整排
    沒人會處理的警告。切窗與命中位置由 `privacy.py` 決定,這裡只做取捨。

    比對用 `in` 而不是相等:切窗取最長的合格窗,`88 4111…` 這種左邊緊鄰
    編號的形狀約十分之一會湊出一個更長的合格窗,它不在清單上,於是一份
    只是引用公告號碼的付款文件會拿到警告。窗裡整段寫著公告號碼,就是這
    份文件寫了公告號碼。
    """
    for offset, digits in iter_payment_card_numbers(text):
        if not any(card in digits for card in TEST_PAYMENT_CARDS):
            yield offset


#: 規則的判準是資料,不是通用迴圈裡以 rule_id 比字串的分支 —— rule_id 打錯
#: 一個字母就會靜默變成不過濾,而同一 rule_id 已有對應多個樣式的先例。
_RULES: tuple[tuple[str, RiskSeverity, _RuleScanner], ...] = (
    ("SR-UNICODE-TAG", RiskSeverity.BLOCKER, _pattern_scanner(_UNICODE_TAG)),
    ("SR-BIDI-OVERRIDE", RiskSeverity.BLOCKER, _pattern_scanner(_BIDI_OVERRIDE)),
    (
        "SR-CONTROL-CHARACTER",
        RiskSeverity.BLOCKER,
        _pattern_scanner(_CONTROL_CHARACTER),
    ),
    (
        "SR-BIDI-FORMATTING",
        RiskSeverity.WARNING,
        _pattern_scanner(_BIDI_FORMATTING),
    ),
    (
        "SR-ZERO-WIDTH-FORMATTING",
        RiskSeverity.WARNING,
        _pattern_scanner(_ZERO_WIDTH_FORMATTING, _is_not_leading_bom),
    ),
    (
        "SR-INSTRUCTION-OVERRIDE-TEXT",
        RiskSeverity.WARNING,
        _pattern_scanner(_INSTRUCTION_OVERRIDE_TEXT),
    ),
    (
        "SR-CONTROL-TOKEN-TEXT",
        RiskSeverity.WARNING,
        _pattern_scanner(_CONTROL_TOKEN_TEXT),
    ),
    ("SR-SECRET-VALUE", RiskSeverity.BLOCKER, _pattern_scanner(SECRET_MATERIAL)),
    (
        "SR-CREDENTIAL-REFERENCE",
        RiskSeverity.WARNING,
        _pattern_scanner(CREDENTIAL_REFERENCE),
    ),
    ("SR-CONTACT-PII", RiskSeverity.WARNING, _pattern_scanner(CONTACT_PII)),
    ("SR-PII-VALUE", RiskSeverity.WARNING, _pattern_scanner(PII_VALUE)),
    ("SR-PAYMENT-CARD", RiskSeverity.WARNING, _payment_card_scanner),
)


class SourceRiskInputError(ValueError):
    """The manifest and local source package cannot be inspected safely."""


def source_binding_digest(manifest: Manifest) -> str:
    """Return the stable identity of the local source package risk-scanned."""
    payload = [
        {
            "relative_path": source.relative_path,
            "mime_type": source.mime_type,
            "source_format": source.source_format.value,
            "size_bytes": source.size_bytes,
            "sha256": source.sha256,
            "supported": source.supported,
            "status": source.status.value,
            "duplicate_of": source.duplicate_of,
        }
        for source in manifest.local_sources
    ]
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _scan_source_findings(
    text: str,
    source_ref: str,
    *,
    limit: int,
    warning_limit: int,
) -> tuple[list[SourceRiskFinding], bool, bool]:
    match_heap: list[
        tuple[
            int,
            str,
            int,
            RiskSeverity,
            Iterator[int],
        ]
    ] = []
    for rule_index, (rule_id, severity, scan) in enumerate(_RULES):
        offsets = scan(text)
        try:
            first = next(offsets)
        except StopIteration:
            continue
        heapq.heappush(
            match_heap,
            (first, rule_id, rule_index, severity, offsets),
        )

    findings: list[SourceRiskFinding] = []
    warnings_emitted = 0
    warnings_truncated = False
    line = 1
    line_start = 0
    previous_offset = 0
    while match_heap and len(findings) < limit:
        offset, rule_id, rule_index, severity, offsets = heapq.heappop(match_heap)
        if severity is RiskSeverity.WARNING and warnings_emitted >= warning_limit:
            # 額度用盡就整條規則退場,而不是繼續比對再丟棄 —— 一份高密度
            # 警告來源否則會讓迴圈跑完每一個命中。Blocker 規則不受影響。
            warnings_truncated = True
            continue
        newlines = text.count("\n", previous_offset, offset)
        if newlines:
            line += newlines
            line_start = text.rfind("\n", previous_offset, offset) + 1
        previous_offset = offset
        findings.append(
            SourceRiskFinding(
                rule_id=rule_id,
                severity=severity,
                source_ref=source_ref,
                locator=f"line {line}, column {offset - line_start + 1}",
            )
        )
        if severity is RiskSeverity.WARNING:
            warnings_emitted += 1
        try:
            next_offset = next(offsets)
        except StopIteration:
            continue
        heapq.heappush(
            match_heap,
            (next_offset, rule_id, rule_index, severity, offsets),
        )
    return findings, bool(match_heap), warnings_truncated


def _read_manifest_source(
    sources_root: Path,
    relative_path: str,
    source_ref: str,
    expected_size: int,
    expected_sha256: str,
) -> bytes:
    if expected_size < 0:
        raise SourceRiskInputError(
            f"source-risk manifest size is invalid: {source_ref}"
        )
    parts = relative_path.split("/")
    if (
        not relative_path
        or relative_path.startswith("/")
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise SourceRiskInputError(
            f"source-risk manifest path is unsafe: {source_ref}"
        )
    candidate = sources_root
    for part in parts:
        candidate /= part
        if candidate.is_symlink():
            raise SourceRiskInputError(
                f"source-risk manifest path is a symlink: {source_ref}"
            )
    read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags = read_flags | getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    root_fd = -1
    parent_fd = -1
    file_fd = -1
    try:
        root_fd = os.open(sources_root, directory_flags | nofollow)
        parent_fd = root_fd
        for part in parts[:-1]:
            next_fd = os.open(
                part,
                directory_flags | nofollow,
                dir_fd=parent_fd,
            )
            if parent_fd != root_fd:
                os.close(parent_fd)
            parent_fd = next_fd
        file_fd = os.open(
            parts[-1],
            read_flags | nofollow | nonblock,
            dir_fd=parent_fd,
        )
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise SourceRiskInputError(
                f"source-risk source is not a regular file: {source_ref}"
            )
        remaining = expected_size + 1
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(file_fd, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
    except SourceRiskInputError:
        raise
    except OSError as exc:
        raise SourceRiskInputError(
            f"source-risk source is unreadable: {source_ref}"
        ) from exc
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if parent_fd >= 0 and parent_fd != root_fd:
            os.close(parent_fd)
        if root_fd >= 0:
            os.close(root_fd)
    if len(content) != expected_size:
        raise SourceRiskInputError(
            f"source-risk manifest size mismatch: {source_ref}"
        )
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise SourceRiskInputError(
            f"source-risk manifest digest mismatch: {source_ref}"
        )
    return content


def inspect_source_risks(
    *,
    sources_root: Path,
    manifest: Manifest,
    manifest_sha256: str,
    max_bytes: int,
) -> SourceRiskReport:
    """Inspect every manifest source before any model reads source content."""
    findings: list[SourceRiskFinding] = []
    coverage: list[SourceRiskCoverage] = []
    truncated_source_ref: str | None = None
    warnings_truncated_source_ref: str | None = None

    for source_index, source in enumerate(manifest.local_sources):
        source_ref = f"/local_sources/{source_index}"
        if source.status is not ProcessingStatus.PENDING:
            coverage.append(
                SourceRiskCoverage(
                    source_ref=source_ref,
                    sha256=source.sha256,
                    status=RiskCoverageStatus.SKIPPED,
                    reason=f"manifest status: {source.status.value}",
                )
            )
            continue
        if source.source_format not in _SCANNABLE_FORMATS:
            coverage.append(
                SourceRiskCoverage(
                    source_ref=source_ref,
                    sha256=source.sha256,
                    status=RiskCoverageStatus.UNSCANNABLE,
                    reason=f"source format: {source.source_format.value}",
                )
            )
            finding = SourceRiskFinding(
                rule_id="SR-UNSCANNABLE",
                severity=RiskSeverity.BLOCKER,
                source_ref=source_ref,
                locator="file",
            )
            if len(findings) < MAX_REPORTED_FINDINGS - 1:
                findings.append(finding)
            elif truncated_source_ref is None:
                truncated_source_ref = source_ref
            continue
        if source.size_bytes > max_bytes:
            coverage.append(
                SourceRiskCoverage(
                    source_ref=source_ref,
                    sha256=source.sha256,
                    status=RiskCoverageStatus.UNSCANNABLE,
                    reason="source exceeds max_bytes",
                )
            )
            finding = SourceRiskFinding(
                rule_id="SR-SCAN-SIZE-EXCEEDED",
                severity=RiskSeverity.BLOCKER,
                source_ref=source_ref,
                locator="file",
            )
            if len(findings) < MAX_REPORTED_FINDINGS - 1:
                findings.append(finding)
            elif truncated_source_ref is None:
                truncated_source_ref = source_ref
            continue

        content = _read_manifest_source(
            sources_root,
            source.relative_path,
            source_ref,
            source.size_bytes,
            source.sha256,
        )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            coverage.append(
                SourceRiskCoverage(
                    source_ref=source_ref,
                    sha256=source.sha256,
                    status=RiskCoverageStatus.UNSCANNABLE,
                    reason="source is not valid UTF-8",
                )
            )
            finding = SourceRiskFinding(
                rule_id="SR-INVALID-UTF8",
                severity=RiskSeverity.BLOCKER,
                source_ref=source_ref,
                locator="file",
            )
            if len(findings) < MAX_REPORTED_FINDINGS - 1:
                findings.append(finding)
            elif truncated_source_ref is None:
                truncated_source_ref = source_ref
            continue
        coverage.append(
            SourceRiskCoverage(
                source_ref=source_ref,
                sha256=source.sha256,
                status=RiskCoverageStatus.SCANNED,
            )
        )
        warnings_emitted = sum(
            finding.severity is RiskSeverity.WARNING for finding in findings
        )
        source_findings, source_truncated, source_warnings_truncated = (
            _scan_source_findings(
                text,
                source_ref,
                limit=max(0, MAX_REPORTED_FINDINGS - 1 - len(findings)),
                warning_limit=max(0, MAX_REPORTED_WARNINGS - warnings_emitted),
            )
        )
        findings.extend(source_findings)
        if source_truncated and truncated_source_ref is None:
            truncated_source_ref = source_ref
        if source_warnings_truncated and warnings_truncated_source_ref is None:
            warnings_truncated_source_ref = source_ref

    if warnings_truncated_source_ref is not None:
        findings.append(
            SourceRiskFinding(
                rule_id=_WARNING_TRUNCATION_RULE_ID,
                severity=RiskSeverity.WARNING,
                source_ref=warnings_truncated_source_ref,
                locator="file",
            )
        )
    if truncated_source_ref is not None:
        findings.append(
            SourceRiskFinding(
                rule_id=_TRUNCATION_RULE_ID,
                severity=RiskSeverity.BLOCKER,
                source_ref=truncated_source_ref,
                locator="file",
            )
        )

    verdict = (
        RiskVerdict.REJECT
        if any(finding.severity is RiskSeverity.BLOCKER for finding in findings)
        else RiskVerdict.PASS
    )
    return SourceRiskReport(
        schema_version=SCHEMA_VERSION,
        ruleset_version=RULESET_VERSION,
        max_bytes=max_bytes,
        manifest_sha256=manifest_sha256,
        source_binding_digest=source_binding_digest(manifest),
        verdict=verdict,
        findings=findings,
        coverage=coverage,
    )
