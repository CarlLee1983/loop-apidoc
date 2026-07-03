from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from loop_apidoc import manifest as _manifest_pkg  # noqa: F401  (確保套件已載入)
from loop_apidoc.agentcli.assemble import (
    AssembleInputError,
    backfill_snapshot_files,
    build_extraction_from_files,
    load_extraction_inputs,
    run_assemble_pipeline,
)
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
    UrlSource,
)
from loop_apidoc.preparation.coverage import (
    CoverageResult,
    FetchMethod,
    ResultStatus,
    UrlCoverage,
)
from loop_apidoc.run.models import RunStatus

_INVENTORY = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "§1"}],
    "security_schemes": [],
    "endpoints": [{"method": "GET", "path": "/ping", "summary": "健康檢查",
                   "source": "§2"}],
    "schemas": [],
    "errors": [],
    "operational": [],
    "missing": [],
}
_ENDPOINT = {
    "method": "GET", "path": "/ping",
    "parameters": [], "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [], "missing": [],
}


def _write_extraction(extraction_dir: Path) -> None:
    extraction_dir.mkdir(parents=True, exist_ok=True)
    (extraction_dir / "inventory.json").write_text(
        json.dumps(_INVENTORY, ensure_ascii=False), encoding="utf-8")
    eps = extraction_dir / "endpoints"
    eps.mkdir()
    (eps / "ep0.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8")


def test_load_extraction_inputs_reads_inventory_and_endpoints(tmp_path):
    _write_extraction(tmp_path / "extraction")
    inventory, endpoint_texts, integration = load_extraction_inputs(tmp_path / "extraction")
    assert inventory["overview"] == "Demo API"
    assert len(endpoint_texts) == 1
    assert json.loads(endpoint_texts[0])["path"] == "/ping"


def test_load_extraction_inputs_missing_inventory_raises(tmp_path):
    (tmp_path / "extraction").mkdir()
    with pytest.raises(AssembleInputError):
        load_extraction_inputs(tmp_path / "extraction")


def test_load_extraction_inputs_bad_json_raises(tmp_path):
    d = tmp_path / "extraction"
    d.mkdir()
    (d / "inventory.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(AssembleInputError):
        load_extraction_inputs(d)


def test_build_extraction_from_files_produces_stage_and_endpoint_artifacts(tmp_path):
    store = ExtractionStore(tmp_path / "store")
    extraction = build_extraction_from_files(
        _INVENTORY, [json.dumps(_ENDPOINT, ensure_ascii=False)], store)
    stage_ids = {a.stage_id for a in extraction.artifacts}
    # inventory 切出 03/04/05/07/08/09 + 敘事 01/02/10,per-endpoint 為 06
    assert {"03", "04", "05", "06", "07", "08", "09"} <= stage_ids
    ep06 = [a for a in extraction.artifacts if a.stage_id == "06"]
    assert len(ep06) == 1
    assert json.loads(ep06[0].answer)["path"] == "/ping"


# ── Task 2: run_assemble_pipeline ───────────────────────────────────────────


def test_run_assemble_pipeline_writes_outputs(tmp_path):
    _write_extraction(tmp_path / "extraction")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "manual.md").write_text("# Demo API\nGET /ping", encoding="utf-8")
    out = tmp_path / "out"

    result = run_assemble_pipeline(
        sources_root=sources,
        extraction_dir=tmp_path / "extraction",
        output_root=out,
        run_id="run-test",
        generated_at=datetime(2026, 6, 27, tzinfo=timezone.utc),
        urls=[],
    )

    run_dir = out / "run-test"
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "openapi.yaml").is_file()
    assert (run_dir / "api-guide.zh-TW.md").is_file()
    assert (run_dir / "provenance.json").is_file()
    assert (run_dir / "preparation-report.json").is_file()
    assert (run_dir / "preparation-report.md").is_file()
    assert (run_dir / "plan" / "normalization-plan.json").is_file()
    assert (run_dir / "validation" / "report.json").is_file()
    prep_payload = json.loads(
        (run_dir / "preparation-report.json").read_text(encoding="utf-8")
    )
    assert prep_payload["status"] == "ready"
    assert prep_payload["summary"]["ready"] == 4
    assert result.status in (RunStatus.PASSED, RunStatus.FAILED)
    assert result.run_dir == str(run_dir)


def test_run_assemble_pipeline_bad_input_leaves_no_run_dir(tmp_path):
    # 擷取輸入錯誤(缺 inventory.json)應在寫入任何輸出前就失敗,
    # 不留下孤兒 run 目錄。
    (tmp_path / "extraction").mkdir()  # 空目錄,無 inventory.json
    sources = tmp_path / "sources"
    sources.mkdir()
    out = tmp_path / "out"

    with pytest.raises(AssembleInputError):
        run_assemble_pipeline(
            sources_root=sources,
            extraction_dir=tmp_path / "extraction",
            output_root=out,
            run_id="run-test",
            generated_at=datetime(2026, 6, 27, tzinfo=timezone.utc),
            urls=[],
        )

    assert not (out / "run-test").exists()


# ── Task 3: backfill_snapshot_files ────────────────────────────────────────────

_NOW = datetime(2026, 7, 4, tzinfo=timezone.utc)


def _local(rel: str) -> LocalSource:
    return LocalSource(
        relative_path=rel, mime_type="text/markdown", source_format=SourceFormat.MARKDOWN,
        size_bytes=1, sha256="x", scanned_at=_NOW, supported=True,
        status=ProcessingStatus.PENDING,
    )


def _url(url: str) -> UrlSource:
    return UrlSource(url=url, fetched_at=_NOW, http_status=200)


def _manifest(locals_, urls) -> Manifest:
    return Manifest(sources_root="/src", generated_at=_NOW,
                    local_sources=locals_, url_sources=urls)


def _coverage(results) -> UrlCoverage:
    return UrlCoverage(entry_url="https://a.example/", results=results)


def test_backfill_unique_suffix_match_sets_snapshot_file():
    manifest = _manifest([_local("overview.md")], [_url("https://a.example/overview")])
    coverage = _coverage([
        CoverageResult(url="https://a.example/overview/", status=ResultStatus.FETCHED,
                       file="sources/overview.md", method=FetchMethod.DEFUDDLE),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    assert out.url_sources[0].snapshot_file == "overview.md"
    # 純函式:原 manifest 不被就地修改
    assert manifest.url_sources[0].snapshot_file is None


def test_backfill_normalizes_url_before_match():
    manifest = _manifest([_local("overview.md")], [_url("https://a.example/overview#top")])
    coverage = _coverage([
        CoverageResult(url="https://a.example/overview", status=ResultStatus.FETCHED_RENDERED,
                       file="sources/overview.md"),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    assert out.url_sources[0].snapshot_file == "overview.md"


def test_backfill_auth_required_with_file_maps():
    manifest = _manifest([_local("overview.md")], [_url("https://a.example/overview")])
    coverage = _coverage([
        CoverageResult(url="https://a.example/overview", status=ResultStatus.AUTH_REQUIRED,
                       file="sources/overview.md"),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    assert out.url_sources[0].snapshot_file == "overview.md"


def test_backfill_result_without_file_leaves_none():
    manifest = _manifest([_local("overview.md")], [_url("https://a.example/overview")])
    coverage = _coverage([
        CoverageResult(url="https://a.example/overview", status=ResultStatus.FETCH_FAILED,
                       file=None),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    assert out.url_sources[0].snapshot_file is None


def test_backfill_zero_match_leaves_none():
    manifest = _manifest([_local("overview.md")], [_url("https://a.example/other")])
    coverage = _coverage([
        CoverageResult(url="https://a.example/overview", status=ResultStatus.FETCHED,
                       file="sources/overview.md"),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    assert out.url_sources[0].snapshot_file is None


def test_backfill_ambiguous_suffix_leaves_none():
    # 帳本 file 後綴同時命中兩個本地檔 → 多重命中 → None
    manifest = _manifest(
        [_local("overview.md"), _local("docs/overview.md")],
        [_url("https://a.example/overview")],
    )
    coverage = _coverage([
        CoverageResult(url="https://a.example/overview", status=ResultStatus.FETCHED,
                       file="sources/docs/overview.md"),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    # "sources/docs/overview.md" 後綴命中 "docs/overview.md" 與 "overview.md" 兩者 → 模糊
    assert out.url_sources[0].snapshot_file is None


def test_backfill_multiple_results_to_different_files_leaves_none():
    manifest = _manifest([_local("a.md"), _local("b.md")], [_url("https://a.example/p")])
    coverage = _coverage([
        CoverageResult(url="https://a.example/p", status=ResultStatus.FETCHED, file="sources/a.md"),
        CoverageResult(url="https://a.example/p", status=ResultStatus.FETCHED, file="sources/b.md"),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    assert out.url_sources[0].snapshot_file is None


def _mock_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>overview</body></html>")
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_pipeline_backfills_snapshot_file_into_manifest(tmp_path, monkeypatch):
    from loop_apidoc.agentcli import assemble as assemble_mod

    _write_extraction(tmp_path / "extraction")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "overview.md").write_text("# Demo API\nGET /ping", encoding="utf-8")

    # coverage 帳本:entry URL 對應 sources/overview.md 快照
    cov = tmp_path / "coverage.json"
    cov.write_text(json.dumps({
        "entry_url": "https://a.example/overview",
        "confirmed_by_user": True,
        "expected": [{"url": "https://a.example/overview", "source": "user"}],
        "results": [{"url": "https://a.example/overview", "status": "fetched",
                     "file": "sources/overview.md", "method": "defuddle"}],
    }), encoding="utf-8")

    # build_manifest 內部會探測 URL — 用 MockTransport 攔截,避免真網路。
    real_build = assemble_mod.build_manifest

    def fake_build(*, sources_root, urls, generated_at):
        return real_build(sources_root=sources_root, urls=urls,
                          generated_at=generated_at, client=_mock_client())

    monkeypatch.setattr(assemble_mod, "build_manifest", fake_build)

    out = tmp_path / "out"
    assemble_mod.run_assemble_pipeline(
        sources_root=sources,
        extraction_dir=tmp_path / "extraction",
        output_root=out,
        run_id="run-cov",
        generated_at=datetime(2026, 7, 4, tzinfo=timezone.utc),
        urls=["https://a.example/overview"],
        url_coverage_path=cov,
    )

    manifest_payload = json.loads(
        (out / "run-cov" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["url_sources"][0]["snapshot_file"] == "overview.md"


def test_pipeline_without_coverage_leaves_snapshot_file_none(tmp_path, monkeypatch):
    from loop_apidoc.agentcli import assemble as assemble_mod

    _write_extraction(tmp_path / "extraction")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "overview.md").write_text("# Demo API\nGET /ping", encoding="utf-8")

    real_build = assemble_mod.build_manifest

    def fake_build(*, sources_root, urls, generated_at):
        return real_build(sources_root=sources_root, urls=urls,
                          generated_at=generated_at, client=_mock_client())

    monkeypatch.setattr(assemble_mod, "build_manifest", fake_build)

    out = tmp_path / "out"
    assemble_mod.run_assemble_pipeline(
        sources_root=sources,
        extraction_dir=tmp_path / "extraction",
        output_root=out,
        run_id="run-nocov",
        generated_at=datetime(2026, 7, 4, tzinfo=timezone.utc),
        urls=["https://a.example/overview"],
        url_coverage_path=None,
    )

    manifest_payload = json.loads(
        (out / "run-nocov" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["url_sources"][0]["snapshot_file"] is None
