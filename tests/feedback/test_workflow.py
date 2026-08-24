from __future__ import annotations

import json

import pytest

from loop_apidoc.feedback.errors import FeedbackInputError
from loop_apidoc.feedback.loader import load_observation_bundle
from loop_apidoc.feedback.workflow import (
    AssessFeedbackCommand,
    FeedbackWorkflow,
    SubmitFeedbackCommand,
)
from tests.test_cli_feedback import _approved_contract, _bundle_payload, _foundry_bytes


def test_workflow_assesses_and_submits_a_deterministic_feedback_case(tmp_path) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    bundle_path = tmp_path / "feedback-bundle.json"
    bundle_path.write_text(
        json.dumps(_bundle_payload(asset_id, contract, observed="201")),
        encoding="utf-8",
    )
    workflow = FeedbackWorkflow()
    bundle = load_observation_bundle(bundle_path)

    assessed = workflow.assess(
        AssessFeedbackCommand(
            project_root=tmp_path,
            docset_id="demo-api",
            asset_id=asset_id,
            bundle=bundle,
        )
    )
    submitted = workflow.submit(
        SubmitFeedbackCommand(
            project_root=tmp_path,
            docset_id="demo-api",
            bundle=bundle,
            assessment=assessed.assessment,
        )
    )

    assert assessed.assessment.open_discrepancy_count == 1
    assert submitted.case.assessment_id == assessed.assessment.assessment_id


def test_workflow_rejects_a_forged_assessment_before_governed_write(tmp_path) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    bundle_path = tmp_path / "feedback-bundle.json"
    bundle_path.write_text(
        json.dumps(_bundle_payload(asset_id, contract, observed="201")),
        encoding="utf-8",
    )
    workflow = FeedbackWorkflow()
    bundle = load_observation_bundle(bundle_path)
    assessed = workflow.assess(
        AssessFeedbackCommand(
            project_root=tmp_path,
            docset_id="demo-api",
            asset_id=asset_id,
            bundle=bundle,
        )
    )
    before = _foundry_bytes(tmp_path)

    with pytest.raises(FeedbackInputError, match="deterministic reassessment"):
        workflow.submit(
            SubmitFeedbackCommand(
                project_root=tmp_path,
                docset_id="demo-api",
                bundle=bundle,
                assessment=assessed.assessment.model_copy(
                    update={"assessment_id": "forged"}
                ),
            )
        )

    assert _foundry_bytes(tmp_path) == before
