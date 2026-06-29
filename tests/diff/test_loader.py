from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from loop_apidoc.diff.loader import DiffInputError, load_run_artifacts
from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.validate.models import ValidationReport

_NOW = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "paths": {},
    }


def write_run(run_dir: Path, *, integration: dict | None = None) -> Path:
    run_dir.mkdir(parents=True)
    (run_dir / "openapi.yaml").write_text(
        yaml.safe_dump(_openapi(), sort_keys=False),
        encoding="utf-8",
    )
    provenance = ProvenanceDocument(
        notebook_url="",
        entries=[
            ProvenanceEntry(
                target="info.title",
                status=PlanItemStatus.SUPPORTED,
                manifest_source="manual.md",
                query_id="01",
                answer_path="answers/01.txt",
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
    if integration is not None:
        (run_dir / "integration-contract.json").write_text(
            json.dumps(integration, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return run_dir


def test_load_run_artifacts_reads_required_and_optional_files(tmp_path):
    run_dir = write_run(
        tmp_path / "run",
        integration={"version": "1.0", "crypto": [{"name": "sig"}]},
    )

    artifacts = load_run_artifacts(run_dir)

    assert artifacts.run_dir == run_dir
    assert artifacts.openapi["info"]["title"] == "Demo"
    assert artifacts.integration == {"version": "1.0", "crypto": [{"name": "sig"}]}
    assert artifacts.provenance.entries[0].target == "info.title"
    assert artifacts.validation.ok is True
    assert artifacts.manifest.local_sources[0].relative_path == "manual.md"


def test_load_run_artifacts_allows_missing_integration_contract(tmp_path):
    artifacts = load_run_artifacts(write_run(tmp_path / "run"))
    assert artifacts.integration is None


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("openapi.yaml", "openapi.yaml"),
        ("provenance.json", "provenance.json"),
        ("validation/report.json", "validation/report.json"),
        ("manifest.json", "manifest.json"),
    ],
)
def test_load_run_artifacts_rejects_missing_required_artifact(
    tmp_path,
    relative_path,
    message,
):
    run_dir = write_run(tmp_path / "run")
    (run_dir / relative_path).unlink()

    with pytest.raises(DiffInputError) as excinfo:
        load_run_artifacts(run_dir)

    assert message in str(excinfo.value)


def test_load_run_artifacts_rejects_bad_yaml(tmp_path):
    run_dir = write_run(tmp_path / "run")
    (run_dir / "openapi.yaml").write_text("a: b:\n  - broken", encoding="utf-8")

    with pytest.raises(DiffInputError) as excinfo:
        load_run_artifacts(run_dir)

    assert "openapi.yaml" in str(excinfo.value)


def test_load_run_artifacts_rejects_non_object_integration(tmp_path):
    run_dir = write_run(tmp_path / "run")
    (run_dir / "integration-contract.json").write_text("[]", encoding="utf-8")

    with pytest.raises(DiffInputError) as excinfo:
        load_run_artifacts(run_dir)

    assert "integration-contract.json" in str(excinfo.value)


@pytest.mark.parametrize(
    "relative_path",
    ["provenance.json", "validation/report.json", "manifest.json"],
)
def test_load_run_artifacts_schema_error_names_the_file(tmp_path, relative_path):
    run_dir = write_run(tmp_path / "run")
    (run_dir / relative_path).write_text("123", encoding="utf-8")

    with pytest.raises(DiffInputError) as excinfo:
        load_run_artifacts(run_dir)

    assert relative_path in str(excinfo.value)
