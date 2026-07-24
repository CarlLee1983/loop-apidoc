from __future__ import annotations

import json

from typer.testing import CliRunner

from loop_apidoc.cli import app


runner = CliRunner()


def _replay(*, runtime: str, precision: float, cost: float | None) -> dict:
    return {
        "case_id": "payment-v1",
        "case_version": "1",
        "runtime_identity": runtime,
        "runtime_version": "2026-07",
        "domain_version": "1",
        "metrics": {
            "claim_precision": precision,
            "claim_recall": 0.8,
            "unsupported_assertion_rate": 1 - precision,
            "evidence_reference_correctness": 1.0,
            "field_omission_rate": 0.2,
            "conflict_detection_recall": 1.0,
            "semantic_support_precision": 0.9,
            "semantic_support_recall": 0.7,
            "claim_path_coverage": 0.8,
            "contradiction_detection_recall": 1.0,
            "relationship_classification_accuracy": 0.75,
        },
        "cost": cost,
        "latency_ms": None,
        "diagnostics": [],
    }


def test_evaluate_compares_versioned_runtime_results_and_writes_reports(tmp_path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    output = tmp_path / "evaluation"
    baseline.write_text(json.dumps(_replay(runtime="baseline", precision=0.6, cost=1.25)))
    candidate.write_text(json.dumps(_replay(runtime="candidate", precision=0.9, cost=None)))

    result = runner.invoke(
        app,
        [
            "evaluate",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["case"] == {"id": "payment-v1", "version": "1"}
    assert payload["metrics"]["claim_precision_delta"] == 0.3
    assert payload["metrics"]["relationship_classification_accuracy_delta"] == 0.0
    assert payload["cost_delta"] is None
    assert payload["latency_ms_delta"] is None
    assert (output / "evaluation-report.json").is_file()
    assert (output / "evaluation-report.md").is_file()


def test_evaluate_rejects_results_for_different_case_versions_without_writing(tmp_path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    output = tmp_path / "evaluation"
    baseline.write_text(json.dumps(_replay(runtime="baseline", precision=0.6, cost=1.25)))
    mismatched = _replay(runtime="candidate", precision=0.9, cost=1.5)
    mismatched["case_version"] = "2"
    candidate.write_text(json.dumps(mismatched))

    result = runner.invoke(
        app,
        [
            "evaluate",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2
    assert "same case id and version" in result.stderr
    assert not output.exists()
