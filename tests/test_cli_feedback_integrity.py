from __future__ import annotations

import json
from pathlib import Path

from tests.test_cli_feedback import _approved_contract, _bundle_payload, app, runner


def test_feedback_submit_recomputes_assessment_before_persistence(
    tmp_path: Path,
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(
        json.dumps(_bundle_payload(asset_id, contract, observed="201"), indent=2),
        encoding="utf-8",
    )
    assessment_dir = tmp_path / "assessment"
    assessed = runner.invoke(
        app,
        [
            "feedback", "assess", "--project", str(tmp_path), "--docset", "demo-api",
            "--asset", asset_id, "--bundle", str(bundle), "--output", str(assessment_dir),
        ],
    )
    assert assessed.exit_code == 1, assessed.output
    assessment_path = assessment_dir / "feedback-assessment.json"
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    assessment["route"] = "implementation_correction"
    assessment_path.write_text(json.dumps(assessment, indent=2), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "feedback", "submit", "--project", str(tmp_path), "--docset", "demo-api",
            "--bundle", str(bundle), "--assessment", str(assessment_path),
        ],
    )

    assert result.exit_code == 2, result.output
    assert "does not match deterministic reassessment" in result.output
    assert not (
        tmp_path / ".foundry/api/docsets/demo-api/feedback/cases"
    ).exists()


def test_feedback_review_records_non_approval_route_without_proposal(
    tmp_path: Path,
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(
        json.dumps(_bundle_payload(asset_id, contract, observed="201"), indent=2),
        encoding="utf-8",
    )
    assessment_dir = tmp_path / "assessment"
    assessed = runner.invoke(
        app,
        [
            "feedback", "assess", "--project", str(tmp_path), "--docset", "demo-api",
            "--asset", asset_id, "--bundle", str(bundle), "--output", str(assessment_dir),
        ],
    )
    assert assessed.exit_code == 1, assessed.output
    assessment_path = assessment_dir / "feedback-assessment.json"
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    submitted = runner.invoke(
        app,
        [
            "feedback", "submit", "--project", str(tmp_path), "--docset", "demo-api",
            "--bundle", str(bundle), "--assessment", str(assessment_path),
        ],
    )
    assert submitted.exit_code == 0, submitted.output

    reviewed = runner.invoke(
        app,
        [
            "feedback", "review", "--project", str(tmp_path), "--docset", "demo-api",
            "--case", assessment["assessment_id"], "--reviewed-by", "contract-reviewer",
            "--reviewer-version", "1", "--at", "2026-08-02T10:30:00Z",
            "--disposition", "needs_evidence", "--route", "provider_clarification",
        ],
    )

    assert reviewed.exit_code == 0, reviewed.output
    decision_path = (
        tmp_path
        / ".foundry/api/docsets/demo-api/feedback/cases"
        / assessment["assessment_id"]
        / "review/decision.json"
    )
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["disposition"] == "needs_evidence"
    assert decision["requested_route"] == "provider_clarification"


def test_feedback_submit_recomputes_proposal_before_persistence(
    tmp_path: Path,
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(
        json.dumps(_bundle_payload(asset_id, contract, observed="201"), indent=2),
        encoding="utf-8",
    )
    assessment_dir = tmp_path / "assessment"
    assert runner.invoke(
        app,
        [
            "feedback", "assess", "--project", str(tmp_path), "--docset", "demo-api",
            "--asset", asset_id, "--bundle", str(bundle), "--output", str(assessment_dir),
        ],
    ).exit_code == 1
    proposals_dir = tmp_path / "proposals"
    assert runner.invoke(
        app,
        [
            "feedback", "propose", "--assessment",
            str(assessment_dir / "feedback-assessment.json"), "--at",
            "2026-08-02T10:05:00Z", "--output", str(proposals_dir),
        ],
    ).exit_code == 0
    proposal_path = next(proposals_dir.glob("proposal-*.json"))
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["proposed_value"] = "418"
    proposal_path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "feedback", "submit", "--project", str(tmp_path), "--docset", "demo-api",
            "--bundle", str(bundle), "--assessment",
            str(assessment_dir / "feedback-assessment.json"), "--proposal",
            str(proposal_path),
        ],
    )

    assert result.exit_code == 2, result.output
    assert "does not match deterministic proposal" in result.output
