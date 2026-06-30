from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.score.loader import load_score_inputs
from loop_apidoc.score.models import ScoreInputError
from loop_apidoc.validate.models import ValidationReport

_NOW = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "paths": {"/ping": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }


def write_score_run(run_dir: Path, *, include_plan: bool = True) -> Path:
    run_dir.mkdir(parents=True)
    (run_dir / "openapi.yaml").write_text(
        yaml.safe_dump(_openapi(), sort_keys=False),
        encoding="utf-8",
    )
    provenance = ProvenanceDocument(
        notebook_url="",
        entries=[
            ProvenanceEntry(
                target="paths./ping.get",
                status=PlanItemStatus.SUPPORTED,
                manifest_source="manual.md",
                query_id="06",
                answer_path="answers/06.txt",
                locator="p.1",
            )
        ],
    )
    (run_dir / "provenance.json").write_text(
        provenance.model_dump_json(indent=2),
        encoding="utf-8",
    )
    validation_dir = run_dir / "validation"
    validation_dir.mkdir()
    (validation_dir / "report.json").write_text(
        ValidationReport().model_dump_json(indent=2),
        encoding="utf-8",
    )
    (validation_dir / "report.md").write_text("# Validation\n", encoding="utf-8")
    manifest = Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=10,
                sha256="abc",
                scanned_at=_NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )
    if include_plan:
        (run_dir / "plan").mkdir()
        (run_dir / "plan" / "normalization-plan.json").write_text(
            json.dumps({"endpoints": [{"path": "/ping"}]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (run_dir / "review.html").write_text("<html></html>", encoding="utf-8")
    return run_dir


def test_load_score_inputs_reads_required_and_optional_artifacts(tmp_path: Path) -> None:
    run_dir = write_score_run(tmp_path / "run")

    inputs = load_score_inputs(run_dir)

    assert inputs.run_dir == run_dir
    assert inputs.openapi["info"]["title"] == "Demo"
    assert inputs.validation.ok is True
    assert inputs.provenance.entries[0].target == "paths./ping.get"
    assert inputs.manifest.local_sources[0].relative_path == "manual.md"
    assert inputs.plan == {"endpoints": [{"path": "/ping"}]}
    assert inputs.review_html_exists is True
    assert inputs.validation_markdown_exists is True


def test_load_score_inputs_allows_missing_plan(tmp_path: Path) -> None:
    inputs = load_score_inputs(write_score_run(tmp_path / "run", include_plan=False))
    assert inputs.plan is None


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("openapi.yaml", "openapi.yaml"),
        ("provenance.json", "provenance.json"),
        ("validation/report.json", "validation/report.json"),
        ("manifest.json", "manifest.json"),
    ],
)
def test_load_score_inputs_rejects_missing_required_file(
    tmp_path: Path,
    relative_path: str,
    message: str,
) -> None:
    run_dir = write_score_run(tmp_path / "run")
    (run_dir / relative_path).unlink()

    with pytest.raises(ScoreInputError) as excinfo:
        load_score_inputs(run_dir)

    assert message in str(excinfo.value)


def test_load_score_inputs_rejects_invalid_openapi_yaml(tmp_path: Path) -> None:
    run_dir = write_score_run(tmp_path / "run")
    (run_dir / "openapi.yaml").write_text("a: b:\n  - broken", encoding="utf-8")

    with pytest.raises(ScoreInputError) as excinfo:
        load_score_inputs(run_dir)

    assert "openapi.yaml" in str(excinfo.value)


@pytest.mark.parametrize(
    "relative_path",
    ["provenance.json", "validation/report.json", "manifest.json"],
)
def test_load_score_inputs_schema_error_names_file(
    tmp_path: Path,
    relative_path: str,
) -> None:
    run_dir = write_score_run(tmp_path / "run")
    (run_dir / relative_path).write_text("123", encoding="utf-8")

    with pytest.raises(ScoreInputError) as excinfo:
        load_score_inputs(run_dir)

    assert relative_path in str(excinfo.value)


def test_load_score_inputs_invalid_optional_plan_names_file(tmp_path: Path) -> None:
    run_dir = write_score_run(tmp_path / "run")
    (run_dir / "plan" / "normalization-plan.json").write_text("{", encoding="utf-8")

    with pytest.raises(ScoreInputError) as excinfo:
        load_score_inputs(run_dir)

    assert "plan/normalization-plan.json" in str(excinfo.value)
