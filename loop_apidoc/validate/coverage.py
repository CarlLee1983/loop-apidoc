from __future__ import annotations

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.validate.models import Issue, IssueCode, Severity


def check_manifest_coverage(manifest: Manifest) -> list[Issue]:
    """§6 來源涵蓋檢查：把無法納入規格化的本機來源浮現為 issue。

    - UNREADABLE 來源 → ERROR（讀取失敗、零資訊的 coverage gap）。
    - UNSUPPORTED 來源 → WARNING（格式不支援，浮現但不阻擋）。
    - DUPLICATE／PENDING 不浮現。

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
    return issues
