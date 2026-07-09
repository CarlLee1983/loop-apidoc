from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.agentcli.source_guard import (
    check_extraction_inputs,
    path_violations,
    source_violations,
    summary_violations,
)
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)

_AT = datetime(2026, 7, 9, tzinfo=timezone.utc)


def _local(path: str) -> LocalSource:
    return LocalSource(
        relative_path=path,
        mime_type="application/pdf",
        source_format=SourceFormat.PDF,
        size_bytes=1,
        sha256="a" * 64,
        scanned_at=_AT,
        supported=True,
        status=ProcessingStatus.PENDING,
    )


def _manifest(*paths: str) -> Manifest:
    return Manifest(
        sources_root="/s", generated_at=_AT,
        local_sources=[_local(p) for p in paths],
    )


# ── path 規則 ─────────────────────────────────────────────────────────

def test_path_with_base_url_prefix_is_a_violation():
    inventory = {"endpoints": [{"method": "POST", "path": "{api_url}/hrxt/loginGame"}]}

    violations = path_violations(inventory, [])

    assert len(violations) == 1
    assert "inventory.json" in violations[0]
    assert "endpoints[0].path" in violations[0]
    assert "{api_url}/hrxt/loginGame" in violations[0]


def test_rooted_path_and_path_parameters_pass():
    inventory = {"endpoints": [
        {"path": "/hrxt/loginGame"},
        {"path": "/users/{userId}/orders"},
    ]}

    assert path_violations(inventory, []) == []


def test_null_path_is_allowed_for_webhooks():
    """callbacks/webhooks 的 path 依規格為 null，不得誤擋。"""
    assert path_violations({"endpoints": [{"path": None}]}, []) == []


def test_endpoint_file_path_is_checked_and_named():
    violations = path_violations({}, [("ep05.json", {"path": "hrxt/addFreeSpin"})])

    assert len(violations) == 1
    assert "ep05.json" in violations[0]


# ── source 規則 ───────────────────────────────────────────────────────

def test_partially_matching_file_is_left_to_validation():
    """檔案裡多數 source 指名了 manifest 檔，只有一筆引用語料庫外的文件 →
    這是內容問題（validate 報 SOURCE_UNVERIFIED），不是格式契約問題。"""
    manifest = _manifest("overview.md", "events.md")
    inventory = {
        "endpoints": [{"source": "events.md p.2"}],
        "schemas": [{"source": "PayPal REST API reference — webhook-event object"}],
    }

    assert source_violations(inventory, [], None, manifest) == []


def test_endpoint_files_are_one_scope_not_one_per_file():
    """endpoints/*.json 整體視為一個範圍：只要有一個檔正確指名來源，
    其餘檔的可疑引用交給 validate。"""
    manifest = _manifest("a.pdf", "b.pdf")
    endpoints = [("ep0.json", {"source": "a.pdf p.1"}),
                 ("ep1.json", {"source": "某個外部規格"})]

    assert source_violations({}, endpoints, None, manifest) == []


def test_endpoint_files_all_unmatched_is_a_violation():
    manifest = _manifest("a.pdf", "b.pdf")
    endpoints = [("ep0.json", {"source": "第 1 節"}),
                 ("ep1.json", {"source": "第 2 節"})]

    violations = source_violations({}, endpoints, None, manifest)

    assert len(violations) == 2
    assert any("ep0.json" in v for v in violations)


def test_source_not_matching_any_manifest_source_is_a_violation():
    manifest = _manifest("HRXT.pdf", "other.pdf")
    integration = {"crypto": [{"name": "sign", "source": "## 2.4 钱包存款 (line 331)"}]}

    violations = source_violations({}, [], integration, manifest)

    assert len(violations) == 1
    assert "integration.json" in violations[0]
    assert "crypto[0].source" in violations[0]


def test_source_naming_a_manifest_file_passes():
    manifest = _manifest("HRXT.pdf", "other.pdf")
    integration = {"crypto": [{"name": "sign", "source": "HRXT.pdf p.10 — ## 2.4"}]}

    assert source_violations({}, [], integration, manifest) == []


def test_single_document_manifest_skips_the_check_entirely():
    """只有一份可用文件時歸因無歧義（sole_source），維持現行寬鬆行為，
    否則所有既有單源 run 會從 PASS 變成 exit 2。"""
    manifest = _manifest("manual.md")
    inventory = {"environments": [{"name": "prod", "source": "§1"}]}

    assert source_violations(inventory, [], None, manifest) == []


def test_ignored_file_does_not_count_as_a_second_document():
    manifest = _manifest("spec.pdf")
    manifest.local_sources.append(
        LocalSource(
            relative_path="README.md", mime_type="text/markdown",
            source_format=SourceFormat.MARKDOWN, size_bytes=0, sha256="",
            scanned_at=_AT, supported=False, status=ProcessingStatus.IGNORED,
        )
    )

    assert source_violations({"errors": [{"code": "1", "source": "§3"}]}, [], None, manifest) == []


def test_all_source_bearing_inventory_sections_are_checked():
    """整份 inventory.json 無一 source 命中 → 格式契約未被遵守，逐欄位列出。"""
    manifest = _manifest("a.pdf", "b.pdf")
    inventory = {
        "environments": [{"source": "nope"}],
        "security_schemes": [{"source": "nope"}],
        "endpoints": [{"source": "nope"}],
        "schemas": [{"source": "nope"}],
        "errors": [{"source": "nope"}],
        "operational": [{"source": "nope"}],
    }

    violations = source_violations(inventory, [], None, manifest)

    assert len(violations) == 6
    for section in ("environments", "security_schemes", "endpoints",
                    "schemas", "errors", "operational"):
        assert any(f"{section}[0].source" in v for v in violations)


def test_all_integration_sections_are_checked():
    manifest = _manifest("a.pdf", "b.pdf")
    integration = {
        "crypto": [{"source": "nope"}],
        "callbacks": [{"source": "nope"}],
        "field_conditions": [{"source": "nope"}],
        "test_cases": [{"source": "nope"}],
    }

    violations = source_violations({}, [], integration, manifest)

    assert len(violations) == 4


def test_absent_source_is_left_to_validation():
    """缺 source 是 fail-closed 的 gap（validate 會報 SOURCE_UNVERIFIED），
    不是格式錯誤；邊界只擋格式不合的字串。"""
    manifest = _manifest("a.pdf", "b.pdf")

    assert source_violations({"errors": [{"code": "1"}]}, [], None, manifest) == []


def test_url_source_anchor_matches():
    manifest = Manifest(
        sources_root="/s", generated_at=_AT,
        local_sources=[_local("a.pdf"), _local("b.pdf")],
        url_sources=[],
    )
    integration = {"crypto": [{"source": "b.pdf#signing"}]}

    assert source_violations({}, [], integration, manifest) == []


# ── 聚合 ──────────────────────────────────────────────────────────────

def test_check_reports_every_violation_at_once():
    """一次列出所有違規，而不是遇到第一個就停——修正是一次改寫，不是逐筆 requery。"""
    manifest = _manifest("a.pdf", "b.pdf")
    inventory = {"endpoints": [{"path": "api/x", "source": "nope"}]}

    violations = check_extraction_inputs(inventory, [], None, manifest)

    assert len(violations) == 2


# ── null path 端點必須有 summary(#7 的身份鍵) ────────────────────────

def test_null_path_endpoint_file_without_summary_is_a_violation():
    inventory = {"endpoints": [{"method": "POST", "path": None, "summary": "Notify"}]}
    endpoints = [("ep7.json", {"method": "POST", "path": None})]

    violations = summary_violations(inventory, endpoints)

    assert any("ep7.json" in v and "summary" in v for v in violations)


def test_null_path_inventory_entry_without_summary_is_a_violation():
    inventory = {"endpoints": [{"method": "POST", "path": None}]}
    endpoints = [("ep7.json", {"method": "POST", "path": None, "summary": "Notify"})]

    violations = summary_violations(inventory, endpoints)

    assert any("inventory.json" in v and "endpoints[0].summary" in v
               for v in violations)


def test_null_path_with_summary_passes():
    inventory = {"endpoints": [{"method": "POST", "path": None, "summary": "Notify"}]}
    endpoints = [("ep7.json", {"method": "POST", "path": None, "summary": "Notify"})]

    assert summary_violations(inventory, endpoints) == []


def test_blank_summary_counts_as_absent():
    inventory = {"endpoints": [{"method": "POST", "path": None, "summary": "   "}]}
    endpoints = [("ep7.json", {"method": "POST", "path": None, "summary": "Notify"})]

    violations = summary_violations(inventory, endpoints)

    assert any("inventory.json" in v for v in violations)


def test_real_path_endpoint_needs_no_summary():
    inventory = {"endpoints": [{"method": "GET", "path": "/ping"}]}
    endpoints = [("ep0.json", {"method": "GET", "path": "/ping"})]

    assert summary_violations(inventory, endpoints) == []
