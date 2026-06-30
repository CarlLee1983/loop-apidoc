from __future__ import annotations

from datetime import datetime

import yaml

from loop_apidoc.generate.writer import build_result, generate_outputs
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import (
    EndpointEntry,
    NormalizationPlan,
    PlanItemStatus,
)

_NOW = datetime(2026, 6, 25, 12, 0, 0)


def _plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/ping",
            responses=[{"status": "200", "description": "ok"}])],
    )


def _manifest() -> Manifest:
    return Manifest(sources_root="./s", generated_at=_NOW)


def test_build_result_holds_three_artifacts():
    result = build_result(_plan(), _manifest())
    assert result.openapi["openapi"] == "3.1.0"
    assert result.markdown.startswith("#")
    assert result.provenance.notebook_url == "https://nb/x"


def test_generate_outputs_writes_three_files(tmp_path):
    result = generate_outputs(_plan(), _manifest(), tmp_path)
    openapi_file = tmp_path / "openapi.yaml"
    md_file = tmp_path / "api-guide.zh-TW.md"
    prov_file = tmp_path / "provenance.json"
    assert openapi_file.exists() and md_file.exists() and prov_file.exists()
    loaded = yaml.safe_load(openapi_file.read_text(encoding="utf-8"))
    assert loaded["paths"]["/ping"]["get"]["responses"]["200"]["description"] == "ok"
    assert result.openapi == loaded


def test_generate_outputs_creates_nested_run_dir(tmp_path):
    run_dir = tmp_path / "output" / "run-1"
    generate_outputs(_plan(), _manifest(), run_dir)
    assert (run_dir / "openapi.yaml").exists()


def test_generate_outputs_writes_handoff(tmp_path):
    run_dir = tmp_path / "run"
    result = generate_outputs(_plan(), _manifest(), run_dir)
    assert set(result.handoff) == {
        "handoff/integration-tasks.md",
        "handoff/postman_collection.json",
        "handoff/sdk-hints.json",
    }
    assert (run_dir / "handoff" / "integration-tasks.md").is_file()
    assert (run_dir / "handoff" / "postman_collection.json").is_file()
    assert (run_dir / "handoff" / "sdk-hints.json").is_file()
