from __future__ import annotations

from loop_apidoc.generate.models import ProvenanceDocument
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
                suggested_fix="轉為受支援格式（PDF／Markdown／Word／OpenAPI）或確認可略過",
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
        document_ids.extend(
            source.url
            for source in manifest.url_sources
            if source.http_status is not None
            and 200 <= source.http_status < 300
            and source.snapshot_file not in usable_local_ids
        )
        for document_id in document_ids:
            if document_id not in cited_sources:
                issues.append(
                    Issue(
                        code=IssueCode.SOURCE_UNVERIFIED,
                        severity=Severity.WARNING,
                        location=document_id,
                        evidence="source has no material citation in provenance",
                        suggested_fix=(
                            "Re-read the source and cite its material claims, or explicitly "
                            "exclude it when it is not API evidence."
                        ),
                    )
                )
    return issues
