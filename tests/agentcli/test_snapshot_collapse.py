from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.agentcli.assemble import backfill_snapshot_files, build_extraction_from_files
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
    UrlSource,
)
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.preparation.coverage import CoverageResult, ResultStatus, UrlCoverage

_NOW = datetime(2026, 7, 4, tzinfo=timezone.utc)

# 章節式 locator(非檔名、非完整 URL)——多來源時 match_manifest_source 落空
_INVENTORY = {
    "overview": "Line Pay Online v3",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "線上付款 §1"}],
    "security_schemes": [],
    "endpoints": [{"method": "POST", "path": "/payments/request",
                   "summary": "請求付款", "source": "線上付款 §3"}],
    "schemas": [],
    "errors": [],
    "operational": [],
    "missing": [],
}
_ENDPOINT = {
    "method": "POST", "path": "/payments/request", "parameters": [],
    "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [], "missing": [], "source": "線上付款 §3",
}


def _manifest(url_snapshot: str | None) -> Manifest:
    return Manifest(
        sources_root="/src", generated_at=_NOW,
        local_sources=[LocalSource(
            relative_path="online-api-v3-overview.md", mime_type="text/markdown",
            source_format=SourceFormat.MARKDOWN, size_bytes=1, sha256="x",
            scanned_at=_NOW, supported=True, status=ProcessingStatus.PENDING)],
        url_sources=[UrlSource(url="https://pay.example/online/v3", fetched_at=_NOW,
                               http_status=200, snapshot_file=url_snapshot)],
    )


def _extraction(tmp_path):
    import json
    store = ExtractionStore(tmp_path / "store")
    return build_extraction_from_files(
        _INVENTORY, [json.dumps(_ENDPOINT, ensure_ascii=False)], store)


def test_backfilled_snapshot_collapses_and_removes_unverified(tmp_path):
    # 帳本把 entry URL 映射到單一本地快照檔 → 摺疊為 1 份文件 → 章節式 locator 歸屬回檔
    coverage = UrlCoverage(
        entry_url="https://pay.example/online/v3",
        results=[CoverageResult(url="https://pay.example/online/v3",
                                status=ResultStatus.FETCHED,
                                file="sources/online-api-v3-overview.md")],
    )
    manifest = backfill_snapshot_files(_manifest(None), coverage)
    assert manifest.url_sources[0].snapshot_file == "online-api-v3-overview.md"

    plan = build_normalization_plan(_extraction(tmp_path), manifest)
    assert plan.unverified_items == []


def test_no_ledger_preserves_current_unverified_behavior(tmp_path):
    # 無帳本(snapshot_file=None)→ URL 另計 → 2 份文件 → 章節式 locator 落空 → UNVERIFIED
    manifest = _manifest(None)
    plan = build_normalization_plan(_extraction(tmp_path), manifest)
    assert plan.unverified_items  # 至少一項 UNVERIFIED(現狀維持)
