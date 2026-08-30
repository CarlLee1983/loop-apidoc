from __future__ import annotations

from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.formats import unsupported_remedy
from loop_apidoc.manifest.models import Manifest, ProcessingStatus
from loop_apidoc.validate.models import Issue, IssueCode, Severity


def check_manifest_coverage(
    manifest: Manifest,
    provenance: ProvenanceDocument | None = None,
) -> list[Issue]:
    """§6 來源涵蓋檢查：把無法納入規格化的本機來源浮現為 issue。

    - UNREADABLE 來源 → ERROR（讀取失敗、零資訊的 coverage gap）。
    - UNSUPPORTED 來源 → WARNING（格式不支援，浮現但不阻擋）。
    - supported/readable PENDING 來源在 provenance 零引用 → WARNING。
    - successful URL source 在 provenance 零引用 → WARNING；若其 snapshot 已是
      usable local source，視為同一 logical document，不重複告警。
    - DUPLICATE 不浮現。

    issue code 一律用 SOURCE_UNVERIFIED；location 用來源 relative_path
    （§6 穩定來源識別碼）。修正循環會將之分類為 UNFIXABLE。

    訊息一律繁體中文：validation 報告是產品輸出，依 AGENTS.md 的語言政策屬 zh-TW
    那一側（英文是教學／推廣文件的語言）。這裡曾經三筆中文、一筆英文，同一份報告
    因此以兩種語言對 operator 說話。新增檢查時沿用中文，不要各寫各的。
    """
    issues: list[Issue] = []
    for source in manifest.unreadable():
        issues.append(
            Issue(
                code=IssueCode.SOURCE_UNVERIFIED,
                severity=Severity.ERROR,
                location=source.relative_path,
                evidence="來源無法讀取，內容未納入驗證",
                suggested_fix="確認檔案可讀取後重新掃描",
            )
        )
    for source in manifest.unsupported():
        issues.append(
            Issue(
                code=IssueCode.SOURCE_UNVERIFIED,
                severity=Severity.WARNING,
                location=source.relative_path,
                evidence=f"來源格式不受支援（{source.source_format.value}），未納入規格化",
                # 具名到格式:通則列的四種受支援格式,拿著 .xlsx 或 .doc 的人
                # 一種都做不到,那樣的 remedy 等於沒說(ADR 0012)。
                suggested_fix=unsupported_remedy(source.source_format).zh,
            )
        )
    if provenance is not None:
        cited_sources = {
            entry.manifest_source
            for entry in provenance.entries
            if entry.manifest_source is not None
        }
        usable_local_sources = [
            source.relative_path
            for source in manifest.local_sources
            if source.supported and source.status is ProcessingStatus.PENDING
        ]
        usable_local_ids = set(usable_local_sources)
        document_ids = list(usable_local_sources)
        # The identity, not the fetched URL (issue #158): this list is matched
        # against provenance `manifest_source`, and it is also what
        # `Issue.location` reports back to the operator. De-duplicated because
        # two URL sources differing only in their signature share one identity,
        # and naming the same document twice is noise.
        url_document_ids = dict.fromkeys(
            source.citation_id
            for source in manifest.url_sources
            if source.http_status is not None
            and 200 <= source.http_status < 300
            and source.snapshot_file not in usable_local_ids
        )
        document_ids.extend(url_document_ids)
        for document_id in document_ids:
            if document_id not in cited_sources:
                issues.append(
                    Issue(
                        code=IssueCode.SOURCE_UNVERIFIED,
                        severity=Severity.WARNING,
                        location=document_id,
                        evidence="來源在 provenance 中沒有任何實質引用",
                        suggested_fix=(
                            "重讀這份來源並引用它的實質主張；"
                            "若它不是 API 證據，請明確排除。"
                        ),
                    )
                )
    return issues
