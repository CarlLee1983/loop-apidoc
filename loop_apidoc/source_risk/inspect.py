from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path

from loop_apidoc.manifest.models import Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.source_risk.models import (
    RiskCoverageStatus,
    RiskSeverity,
    RiskVerdict,
    SourceRiskCoverage,
    SourceRiskFinding,
    SourceRiskReport,
)

SCHEMA_VERSION = "1"
RULESET_VERSION = "1"

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

_RULES: tuple[tuple[str, RiskSeverity, re.Pattern[str]], ...] = (
    ("SR-UNICODE-TAG", RiskSeverity.BLOCKER, _UNICODE_TAG),
    ("SR-BIDI-OVERRIDE", RiskSeverity.BLOCKER, _BIDI_OVERRIDE),
    ("SR-CONTROL-CHARACTER", RiskSeverity.BLOCKER, _CONTROL_CHARACTER),
    ("SR-BIDI-FORMATTING", RiskSeverity.WARNING, _BIDI_FORMATTING),
    ("SR-ZERO-WIDTH-FORMATTING", RiskSeverity.WARNING, _ZERO_WIDTH_FORMATTING),
    (
        "SR-INSTRUCTION-OVERRIDE-TEXT",
        RiskSeverity.WARNING,
        _INSTRUCTION_OVERRIDE_TEXT,
    ),
    ("SR-CONTROL-TOKEN-TEXT", RiskSeverity.WARNING, _CONTROL_TOKEN_TEXT),
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


def _locator(text: str, offset: int) -> str:
    line = text.count("\n", 0, offset) + 1
    line_start = text.rfind("\n", 0, offset) + 1
    return f"line {line}, column {offset - line_start + 1}"


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
            findings.append(
                SourceRiskFinding(
                    rule_id="SR-UNSCANNABLE",
                    severity=RiskSeverity.BLOCKER,
                    source_ref=source_ref,
                    locator="file",
                )
            )
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
            findings.append(
                SourceRiskFinding(
                    rule_id="SR-SCAN-SIZE-EXCEEDED",
                    severity=RiskSeverity.BLOCKER,
                    source_ref=source_ref,
                    locator="file",
                )
            )
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
            findings.append(
                SourceRiskFinding(
                    rule_id="SR-INVALID-UTF8",
                    severity=RiskSeverity.BLOCKER,
                    source_ref=source_ref,
                    locator="file",
                )
            )
            continue
        coverage.append(
            SourceRiskCoverage(
                source_ref=source_ref,
                sha256=source.sha256,
                status=RiskCoverageStatus.SCANNED,
            )
        )
        source_findings: list[tuple[int, str, SourceRiskFinding]] = []
        for rule_id, severity, pattern in _RULES:
            for match in pattern.finditer(text):
                if (
                    rule_id == "SR-ZERO-WIDTH-FORMATTING"
                    and match.start() == 0
                    and match.group() == "\ufeff"
                ):
                    continue
                source_findings.append(
                    (
                        match.start(),
                        rule_id,
                        SourceRiskFinding(
                            rule_id=rule_id,
                            severity=severity,
                            source_ref=source_ref,
                            locator=_locator(text, match.start()),
                        ),
                    )
                )
        findings.extend(
            finding
            for _, _, finding in sorted(
                source_findings,
                key=lambda item: (item[0], item[1]),
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
