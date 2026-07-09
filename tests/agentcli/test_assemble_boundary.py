from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.agentcli.assemble import AssembleInputError, run_assemble_pipeline

_NOW = datetime(2026, 7, 9, 10, 0, 0, tzinfo=timezone.utc)

_INVENTORY = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "spec.md p.1"}],
    "security_schemes": [], "schemas": [], "errors": [], "operational": [],
    "endpoints": [{"method": "GET", "path": "/ping", "summary": "健康檢查",
                   "source": "spec.md p.2"}],
    "missing": [],
}
_ENDPOINT = {
    "method": "GET", "path": "/ping", "source": "spec.md p.2",
    "parameters": [], "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [], "missing": [],
}


def _setup(tmp_path: Path, *, inventory=None, endpoint=None, integration=None,
           multi_source: bool = True):
    extraction = tmp_path / "extraction"
    (extraction / "endpoints").mkdir(parents=True)
    (extraction / "inventory.json").write_text(
        json.dumps(inventory or _INVENTORY, ensure_ascii=False), encoding="utf-8")
    (extraction / "endpoints" / "ep0.json").write_text(
        json.dumps(endpoint or _ENDPOINT, ensure_ascii=False), encoding="utf-8")
    if integration is not None:
        (extraction / "integration.json").write_text(
            json.dumps(integration, ensure_ascii=False), encoding="utf-8")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "spec.md").write_text("# Demo API\nGET /ping", encoding="utf-8")
    if multi_source:
        # 兩份文件 → sole_source 為 None → 嚴格比對生效
        (sources / "appendix.md").write_text("# 附錄", encoding="utf-8")
    return sources, extraction, tmp_path / "out"


def _run(sources, extraction, out, run_id="r1", **kw):
    return run_assemble_pipeline(
        sources_root=sources, extraction_dir=extraction, output_root=out,
        run_id=run_id, generated_at=_NOW, **kw,
    )


def test_unrooted_path_fails_before_any_run_dir_exists(tmp_path):
    inventory = {**_INVENTORY, "endpoints": [
        {"method": "POST", "path": "{api_url}/hrxt/loginGame",
         "summary": "登入", "source": "spec.md p.2"}]}
    sources, extraction, out = _setup(tmp_path, inventory=inventory)

    with pytest.raises(AssembleInputError) as exc:
        _run(sources, extraction, out)

    assert "endpoints[0].path" in str(exc.value)
    assert not (out / "r1").exists(), "違規時不得留下孤兒 run 目錄"


def test_unmatched_integration_source_fails_at_the_boundary(tmp_path):
    integration = {"crypto": [{"name": "sign", "algorithm": "AES",
                               "source": "## 2.4 钱包存款 (line 331)"}]}
    sources, extraction, out = _setup(tmp_path, integration=integration)

    with pytest.raises(AssembleInputError) as exc:
        _run(sources, extraction, out)

    assert "integration.json" in str(exc.value)
    assert "crypto[0].source" in str(exc.value)
    assert not (out / "r1").exists()


def test_all_violations_are_reported_in_one_message(tmp_path):
    # 整份 inventory.json 無一 source 指名檔案 → 格式契約未被遵守
    inventory = {**_INVENTORY,
                 "environments": [{"name": "prod", "base_url": "https://api.example.com",
                                   "version": None, "source": "第 1 節"}],
                 "endpoints": [{"method": "GET", "path": "ping",
                                "summary": "x", "source": "來源不明"}]}
    sources, extraction, out = _setup(tmp_path, inventory=inventory)

    with pytest.raises(AssembleInputError) as exc:
        _run(sources, extraction, out)

    message = str(exc.value)
    assert "endpoints[0].path" in message
    assert "endpoints[0].source" in message


def test_single_source_run_keeps_lenient_attribution(tmp_path):
    """單一文件時 locator 不需指名檔名——既有 run 不得因邊界檢查而破功。"""
    inventory = {**_INVENTORY,
                 "environments": [{"name": "prod", "base_url": "https://api.example.com",
                                   "version": None, "source": "§1"}],
                 "endpoints": [{"method": "GET", "path": "/ping",
                                "summary": "健康檢查", "source": "§2"}]}
    endpoint = {**_ENDPOINT, "source": "§2"}
    sources, extraction, out = _setup(
        tmp_path, inventory=inventory, endpoint=endpoint, multi_source=False)

    result = _run(sources, extraction, out)

    assert (out / "r1" / "openapi.yaml").exists()
    assert result.run_id == "r1"


def test_excluded_source_does_not_break_single_document_attribution(tmp_path):
    """README 被 DEFAULT_EXCLUDES 略過後，manifest 仍塌縮成單一文件。"""
    inventory = {**_INVENTORY,
                 "environments": [{"name": "prod", "base_url": "https://api.example.com",
                                   "version": None, "source": "§1"}],
                 "endpoints": [{"method": "GET", "path": "/ping",
                                "summary": "健康檢查", "source": "§2"}]}
    sources, extraction, out = _setup(
        tmp_path, inventory=inventory, endpoint={**_ENDPOINT, "source": "§2"},
        multi_source=False)
    (sources / "README.md").write_text("目錄說明", encoding="utf-8")

    assert _run(sources, extraction, out).run_id == "r1"


def test_excludes_are_passed_through_to_the_scan(tmp_path):
    inventory = {**_INVENTORY,
                 "environments": [{"name": "prod", "base_url": "https://api.example.com",
                                   "version": None, "source": "§1"}],
                 "endpoints": [{"method": "GET", "path": "/ping",
                                "summary": "健康檢查", "source": "§2"}]}
    sources, extraction, out = _setup(
        tmp_path, inventory=inventory, endpoint={**_ENDPOINT, "source": "§2"})

    # appendix.md 排除後只剩 spec.md，寬鬆歸因恢復
    result = _run(sources, extraction, out, excludes=("appendix.*",))

    manifest = json.loads((out / "r1" / "manifest.json").read_text(encoding="utf-8"))
    statuses = {s["relative_path"]: s["status"] for s in manifest["local_sources"]}
    assert statuses["appendix.md"] == "ignored"
    assert result.run_id == "r1"


def test_duplicate_endpoint_files_fail_before_any_run_dir_exists(tmp_path):
    """兩個檔案寫同一個端點 → 跨檔不變式在建立 run 目錄前擋下。"""
    sources, extraction, out = _setup(tmp_path)
    (extraction / "endpoints" / "ep1.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(AssembleInputError) as exc:
        _run(sources, extraction, out)

    assert "ep0.json" in str(exc.value) and "ep1.json" in str(exc.value)
    assert not (out / "r1").exists(), "違規時不得留下孤兒 run 目錄"
