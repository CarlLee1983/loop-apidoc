from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.source_quality.loader import (
    SourceQualityInputError,
    load_assessment_reports,
)
from tests.source_quality_support import write_passing_source_quality


def _write_quality_package(tmp_path: Path) -> Path:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "manual.md").write_text("# Demo API\nGET /ping", encoding="utf-8")
    return write_passing_source_quality(
        sources_root=sources,
        output=tmp_path / "source-quality",
        generated_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )


def _blocker_finding() -> dict[str, object]:
    return {
        "id": "SQ-001",
        "source": "manual.md",
        "locator": "Overview",
        "category": "missing_response_contract",
        "evidence": "The response contract is not documented.",
        "severity": "blocker",
        "affected_scope": ["GET /ping"],
        "required_supplement": "Provide the response contract.",
        "acceptance_criteria": "The response fields are documented.",
        "required_source_refs": ["https://docs.example.com/response-contract"],
    }


def _load_report(path: Path) -> tuple[Path, dict[str, object]]:
    report_path = path / "source-quality-report.json"
    return report_path, json.loads(report_path.read_text(encoding="utf-8"))


def test_load_assessment_reports_rejects_pass_report_with_blocker(
    tmp_path: Path,
) -> None:
    quality = _write_quality_package(tmp_path)
    report_path, report = _load_report(quality)
    report["findings"] = [_blocker_finding()]
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(SourceQualityInputError, match="verdict"):
        load_assessment_reports(quality)


def test_load_assessment_reports_rejects_reject_report_without_blocker(
    tmp_path: Path,
) -> None:
    quality = _write_quality_package(tmp_path)
    report_path, report = _load_report(quality)
    report["verdict"] = "reject"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(SourceQualityInputError, match="verdict"):
        load_assessment_reports(quality)


def test_load_assessment_reports_rejects_stale_required_source_refs(
    tmp_path: Path,
) -> None:
    quality = _write_quality_package(tmp_path)
    report_path, report = _load_report(quality)
    report["findings"] = [_blocker_finding()]
    report["verdict"] = "reject"
    report["required_source_refs"] = ["https://docs.example.com/stale"]
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(SourceQualityInputError, match="required_source_refs"):
        load_assessment_reports(quality)


def test_load_assessment_reports_rejects_unknown_report_fields(tmp_path: Path) -> None:
    quality = _write_quality_package(tmp_path)
    report_path, report = _load_report(quality)
    report["unrecognized"] = True
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(SourceQualityInputError, match="unrecognized"):
        load_assessment_reports(quality)


def test_load_assessment_reports_rejects_unknown_diff_kind(tmp_path: Path) -> None:
    quality = _write_quality_package(tmp_path)
    diff_path = quality / "source-diff.json"
    diff_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "path": "manual.md",
                        "kind": "renamed",
                        "summary": "Source file renamed.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SourceQualityInputError, match="kind"):
        load_assessment_reports(quality)


def test_assessed_reports_round_trip_through_loader_unchanged(tmp_path: Path) -> None:
    quality = _write_quality_package(tmp_path)
    _, expected_report = _load_report(quality)
    expected_diff = json.loads(
        (quality / "source-diff.json").read_text(encoding="utf-8")
    )

    report, diff = load_assessment_reports(quality)

    assert report.model_dump(mode="json") == expected_report
    assert diff.model_dump(mode="json") == expected_diff


def test_assemble_rejects_inconsistent_quality_report_before_creating_run_dir(
    tmp_path: Path,
) -> None:
    quality = _write_quality_package(tmp_path)
    report_path, report = _load_report(quality)
    report["findings"] = [_blocker_finding()]
    report_path.write_text(json.dumps(report), encoding="utf-8")

    extraction = tmp_path / "extraction"
    endpoints = extraction / "endpoints"
    endpoints.mkdir(parents=True)
    (extraction / "inventory.json").write_text(
        json.dumps(
            {
                "overview": "Demo API",
                "environments": [],
                "security_schemes": [],
                "schemas": [],
                "errors": [],
                "operational": [],
                "endpoints": [],
                "missing": [],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "out"

    result = CliRunner().invoke(
        app,
        [
            "assemble",
            "--sources",
            str(tmp_path / "sources"),
            "--extraction",
            str(extraction),
            "--output",
            str(output),
            "--source-quality",
            str(quality),
        ],
    )

    assert result.exit_code == 2
    assert "verdict" in result.output
    assert not output.exists()
