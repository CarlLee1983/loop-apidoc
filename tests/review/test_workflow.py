from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
import yaml

from loop_apidoc.foundry import paths, register, store
from loop_apidoc.foundry.models import Docset, ReviewState
from loop_apidoc.review import (
    HandoffTask,
    ReviewConflictError,
    ReviewDisposition,
    ReviewDraft,
    ReviewInputError,
    ReviewItem,
    ReviewKey,
    ReviewRequest,
    ReviewStateError,
    ReviewWaiver,
    ReviewWorkflow,
)
from loop_apidoc.review.models import ReviewSnapshot, ReviewSubjectKind
from loop_apidoc.review.binding import artifact_digests
from loop_apidoc.score.models import ScoreProfile, ScoreReport, ScoreStatus
from tests.foundry._fixtures import write_run_dir

_NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)


def _workflow(tmp_path: Path) -> ReviewWorkflow:
    register.register_docset(
        tmp_path,
        Docset(docset_id="vendor-payments", title="Payments", provider="vendor", product="pay"),
    )
    return ReviewWorkflow(tmp_path)


def _run(tmp_path: Path, run_id: str, **kwargs: object) -> Path:
    return write_run_dir(tmp_path / "output" / run_id, **kwargs)  # type: ignore[arg-type]


def _request(run: Path) -> ReviewRequest:
    return ReviewRequest(docset_id="vendor-payments", run_dir=run)


def _draft(snapshot: ReviewSnapshot, **kwargs: object) -> ReviewDraft:
    return ReviewDraft(binding=snapshot.binding, **kwargs)


def _write_needs_attention_score(run: Path) -> None:
    (run / "score" / "score.json").write_text(
        ScoreReport(
            status=ScoreStatus.NEEDS_ATTENTION,
            score=65,
            profile=ScoreProfile.REVIEW,
            min_score=70,
            category_scores={},
        ).model_dump_json(),
        encoding="utf-8",
    )


def _write_core_evidence(run: Path, *, target: str) -> None:
    core_dir = run / "core"
    core_dir.mkdir()
    (core_dir / "evidence.json").write_text(json.dumps({
        "source_set_id": "source-set",
        "source_set_version": "1",
        "artifacts": [],
        "fragments": [{
            "id": "fragment-1",
            "source_artifact_id": "source-1",
            "locator": {"kind": "line_range", "start_line": 12, "end_line": 14},
            "fragment_digest": "a" * 64,
            "normalized_excerpt": "POST /ping requires an API key.",
            "precision": "exact",
        }],
    }), encoding="utf-8")
    projection_dir = core_dir / "projections"
    projection_dir.mkdir()
    (projection_dir / "review-data.json").write_text(json.dumps({
        "contract": {},
        "relationships": [{
            "target": target,
            "claim_identity": "operation:/ping:get",
            "claim_path": "/method",
            "relationship_id": "relationship-1",
            "relationship": "explicit_support",
            "fragment_id": "fragment-1",
            "fragment_locator": {"kind": "line_range", "start_line": 12, "end_line": 14},
            "fragment_digest": "digest-1",
            "source_artifact_id": "source-1",
            "source_artifact_digest": "source-digest",
            "source_id": "manual.md",
            "source_locator": "manual.md",
        }],
    }), encoding="utf-8")


def test_open_review_imports_valid_run_and_uses_baseline_without_current(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    run = _run(tmp_path, "20260723T120000.000000Z", validation_ok=False)

    snapshot = workflow.open_review(_request(run))

    assert snapshot.mode.value == "baseline"
    assert snapshot.diff is None
    assert paths.candidate_dir(tmp_path, "vendor-payments", run.name).is_dir()
    assert snapshot.binding.base_asset_id is None


def test_open_review_attaches_verified_exact_evidence_to_matching_validation_subject(
    tmp_path: Path,
) -> None:
    workflow = _workflow(tmp_path)
    run = _run(tmp_path, "20260723T120000.000000Z", validation_ok=False)
    core_dir = run / "core"
    core_dir.mkdir()
    (core_dir / "evidence.json").write_text(
        """{
  "source_set_id": "source-set",
  "source_set_version": "1",
  "artifacts": [],
  "fragments": [{
    "id": "fragment-1",
    "source_artifact_id": "source-1",
    "locator": {"kind": "line_range", "start_line": 12, "end_line": 14},
    "fragment_digest": "a".repeat(64),
    "normalized_excerpt": "POST /ping requires an API key.",
    "precision": "exact"
  }]
}""".replace('"a".repeat(64)', '"' + "a" * 64 + '"'),
        encoding="utf-8",
    )
    projection_dir = core_dir / "projections"
    projection_dir.mkdir()
    (projection_dir / "review-data.json").write_text(
        """{
  "contract": {},
  "relationships": [{
    "target": "paths./ping.get",
    "claim_identity": "operation:/ping:get",
    "claim_path": "/method",
    "relationship_id": "relationship-1",
    "relationship": "explicit_support",
    "fragment_id": "fragment-1",
    "fragment_locator": {"kind": "line_range", "start_line": 12, "end_line": 14},
    "fragment_digest": "digest-1",
    "source_artifact_id": "source-1",
    "source_artifact_digest": "source-digest",
    "source_id": "manual.md",
    "source_locator": "manual.md"
  }, {
    "target": "paths./ping.get",
    "claim_identity": "operation:/ping:get",
    "claim_path": "/security",
    "relationship_id": "relationship-2",
    "relationship": "insufficient",
    "fragment_id": "fragment-1",
    "fragment_locator": {"kind": "line_range", "start_line": 12, "end_line": 14},
    "fragment_digest": "digest-1",
    "source_artifact_id": "source-1",
    "source_artifact_digest": "source-digest",
    "source_id": "manual.md",
    "source_locator": "manual.md"
  }]
}""",
        encoding="utf-8",
    )

    snapshot = workflow.open_review(_request(run))

    subject = snapshot.subjects[0]
    assert subject.location == "paths./ping.get"
    assert [item.model_dump() for item in subject.evidence] == [{
        "claim_identity": "operation:/ping:get",
        "claim_path": "/method",
        "relationship": "explicit_support",
        "source_id": "manual.md",
        "source_locator": "manual.md",
        "fragment_locator": {"kind": "line_range", "start_line": 12, "end_line": 14},
        "fragment_digest": "a" * 64,
        "normalized_excerpt": "POST /ping requires an API key.",
    }, {
        "claim_identity": "operation:/ping:get",
        "claim_path": "/security",
        "relationship": "insufficient",
        "source_id": "manual.md",
        "source_locator": "manual.md",
        "fragment_locator": {"kind": "line_range", "start_line": 12, "end_line": 14},
        "fragment_digest": "a" * 64,
        "normalized_excerpt": "POST /ping requires an API key.",
    }]


def test_open_review_reopens_same_candidate_but_rejects_changed_collision(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    run = _run(tmp_path, "20260723T120000.000000Z")

    first = workflow.open_review(_request(run))
    reopened = workflow.open_review(_request(run))

    assert reopened.binding == first.binding
    openapi = yaml.safe_load((run / "openapi.yaml").read_text(encoding="utf-8"))
    openapi["info"]["version"] = "2.0.0"
    (run / "openapi.yaml").write_text(yaml.safe_dump(openapi), encoding="utf-8")

    with pytest.raises(ReviewInputError, match="candidate collision"):
        workflow.open_review(_request(run))


def test_second_review_compares_candidate_against_current_asset(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    first_run = _run(tmp_path, "20260723T120000.000000Z")
    first = workflow.open_review(_request(first_run))
    workflow.approve_review(first.key, _draft(first), now=_NOW)

    second_run = _run(tmp_path, "20260724T120000.000000Z")
    openapi = yaml.safe_load((second_run / "openapi.yaml").read_text(encoding="utf-8"))
    openapi["paths"]["/refunds"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    (second_run / "openapi.yaml").write_text(yaml.safe_dump(openapi), encoding="utf-8")
    _write_core_evidence(second_run, target="paths./refunds.get")

    snapshot = workflow.open_review(_request(second_run))

    assert snapshot.mode.value == "update"
    assert snapshot.diff is not None
    assert snapshot.diff.summary["additive"] == 1
    assert snapshot.binding.base_asset_id is not None
    diff_subject = next(subject for subject in snapshot.subjects if subject.kind is ReviewSubjectKind.DIFF)
    assert diff_subject.location == "GET /refunds"
    assert diff_subject.evidence[0].claim_path == "/method"


def test_field_diff_requires_an_exact_evidence_target() -> None:
    from loop_apidoc.review.binding import evidence_for_diff_location

    operation_evidence = []
    field_evidence = []
    evidence = {
        "paths./payments.post": operation_evidence,
        "paths./payments.post.requestBody.application/json": field_evidence,
    }

    assert evidence_for_diff_location(
        "POST /payments requestBody.application/json", evidence
    ) is field_evidence
    assert evidence_for_diff_location(
        "POST /payments requestBody.application/xml", evidence
    ) == []


def test_save_decision_rejects_unknown_subject_and_persists_valid_handoff(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    run = _run(tmp_path, "20260723T120000.000000Z", validation_ok=False)
    snapshot = workflow.open_review(_request(run))

    with pytest.raises(ReviewStateError, match="unknown review subject"):
        workflow.save_decision(
            snapshot.key,
            _draft(snapshot, items=[ReviewItem(
                subject_id="validation:not-real",
                subject_kind=ReviewSubjectKind.VALIDATION,
                disposition=ReviewDisposition.ACCEPT,
            )]),
        )

    subject = snapshot.subjects[0]
    saved = workflow.save_decision(
        snapshot.key,
        _draft(
            snapshot,
            items=[ReviewItem(
                subject_id=subject.id,
                subject_kind=subject.kind,
                disposition=ReviewDisposition.NEEDS_EVIDENCE,
                note="Need an authoritative supplier citation.",
            )],
            handoff=[HandoffTask(
                task_id="source-citation",
                instruction="Re-read the supplier authentication section.",
                subject_ids=[subject.id],
            )],
        ),
    )

    decision = store.load_review_decision(tmp_path, "vendor-payments", run.name)
    assert decision is not None
    assert saved.decision == decision
    assert paths.candidate_review_decision_path(tmp_path, "vendor-payments", run.name).is_file()


def test_approval_is_soft_but_marks_current_needs_follow_up_and_copies_decision(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    run = _run(tmp_path, "20260723T120000.000000Z", validation_ok=False)
    snapshot = workflow.open_review(_request(run))
    subject = snapshot.subjects[0]
    draft = _draft(
        snapshot,
        items=[ReviewItem(
            subject_id=subject.id,
            subject_kind=subject.kind,
            disposition=ReviewDisposition.NEEDS_EVIDENCE,
            note="Needs source evidence.",
        )],
        handoff=[HandoffTask(
            task_id="recover-evidence",
            instruction="Ask the agent to find the missing evidence.",
            subject_ids=[subject.id],
        )],
    )

    result = workflow.approve_review(snapshot.key, draft, now=_NOW)

    current = store.load_current(tmp_path, "vendor-payments")
    assert result.needs_follow_up is True
    assert result.open_handoff_count == 1
    assert current is not None
    assert current.review.state is ReviewState.NEEDS_FOLLOW_UP
    asset = store.load_asset(tmp_path, "vendor-payments", current.current_asset)
    assert asset.approved_by is None
    assert asset.review.open_handoff_count == 1
    assert asset.known_gaps
    assert asset.artifacts.review_decision == "artifacts/review/decision.json"
    assert (paths.asset_artifacts_dir(tmp_path, "vendor-payments", asset.asset_id) / "review" / "decision.json").is_file()


def test_clean_baseline_approval_marks_current_reviewed(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    run = _run(tmp_path, "20260723T120000.000000Z")
    snapshot = workflow.open_review(_request(run))

    result = workflow.approve_review(snapshot.key, _draft(snapshot), now=_NOW)

    current = store.load_current(tmp_path, "vendor-payments")
    assert result.needs_follow_up is False
    assert current is not None
    assert current.review.state is ReviewState.REVIEWED


def test_review_persists_an_expiring_waiver_for_explicit_evidence(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    run = _run(tmp_path, "20260723T120000.000000Z", validation_ok=False)
    _write_core_evidence(run, target="paths./ping.get")
    snapshot = workflow.open_review(_request(run))
    subject = snapshot.subjects[0]
    waiver = ReviewWaiver(
        subject_id=subject.id,
        claim_identity="operation:/ping:get",
        reason="Provider remediation is tracked externally.",
        approved_by="reviewer@example.test",
        expires_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    saved = workflow.save_decision(snapshot.key, _draft(snapshot, waivers=[waiver]))

    assert saved.decision is not None
    assert saved.decision.waivers == [waiver]


def test_stale_saved_decision_refuses_to_be_reopened(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    run = _run(tmp_path, "20260723T120000.000000Z")
    snapshot = workflow.open_review(_request(run))
    workflow.save_decision(snapshot.key, _draft(snapshot))
    candidate = paths.candidate_dir(tmp_path, "vendor-payments", run.name)
    openapi = yaml.safe_load((candidate / "openapi.yaml").read_text(encoding="utf-8"))
    openapi["info"]["version"] = "2.0.0"
    (candidate / "openapi.yaml").write_text(yaml.safe_dump(openapi), encoding="utf-8")

    with pytest.raises(ReviewConflictError, match="stale"):
        workflow.save_decision(snapshot.key, _draft(snapshot))


def test_save_decision_rejects_draft_bound_to_changed_candidate(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    run = _run(tmp_path, "20260723T120000.000000Z")
    snapshot = workflow.open_review(_request(run))
    candidate = paths.candidate_dir(tmp_path, "vendor-payments", run.name)
    openapi = yaml.safe_load((candidate / "openapi.yaml").read_text(encoding="utf-8"))
    openapi["info"]["version"] = "2.0.0"
    (candidate / "openapi.yaml").write_text(yaml.safe_dump(openapi), encoding="utf-8")

    with pytest.raises(ReviewConflictError, match="draft is stale"):
        workflow.save_decision(snapshot.key, _draft(snapshot))


def test_low_score_approval_marks_current_needs_follow_up(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    run = _run(tmp_path, "20260723T120000.000000Z")
    _write_needs_attention_score(run)
    snapshot = workflow.open_review(_request(run))

    result = workflow.approve_review(snapshot.key, _draft(snapshot), now=_NOW)

    current = store.load_current(tmp_path, "vendor-payments")
    assert result.needs_follow_up is True
    assert current is not None
    assert current.review.state is ReviewState.NEEDS_FOLLOW_UP
    asset = store.load_asset(tmp_path, "vendor-payments", current.current_asset)
    assert "score 65 is needs_attention (minimum 70)" in asset.known_gaps


def test_review_rejects_invalid_subject_states_and_missing_evidence(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    run = _run(tmp_path, "20260723T120000.000000Z", validation_ok=False)
    snapshot = workflow.open_review(_request(run))
    subject = snapshot.subjects[0]

    duplicate = ReviewItem(
        subject_id=subject.id,
        subject_kind=subject.kind,
        disposition=ReviewDisposition.ACCEPT,
    )
    with pytest.raises(ReviewStateError, match="duplicate"):
        workflow.save_decision(snapshot.key, _draft(snapshot, items=[duplicate, duplicate]))

    with pytest.raises(ReviewStateError, match="handoff references"):
        workflow.save_decision(
            snapshot.key,
            _draft(
                snapshot,
                items=[ReviewItem(
                    subject_id="manual:verify-vendor",
                    subject_kind=ReviewSubjectKind.MANUAL,
                    disposition=ReviewDisposition.NEEDS_EVIDENCE,
                )],
                handoff=[HandoffTask(
                    task_id="unknown",
                    instruction="Needs a subject that exists.",
                    subject_ids=["unknown-subject"],
                )],
            ),
        )

    needs_follow_up, known_gaps, open_count = workflow._review_outcome(
        snapshot,
        _draft(snapshot, items=[ReviewItem(
            subject_id="manual:verify-vendor",
            subject_kind=ReviewSubjectKind.MANUAL,
            disposition=ReviewDisposition.NEEDS_EVIDENCE,
            note="Supplier confirmation is still needed.",
        )]),
    )
    assert needs_follow_up is True
    assert "Supplier confirmation is still needed." in known_gaps
    assert open_count == 0

    with pytest.raises(ReviewInputError, match="candidate not found"):
        workflow.save_decision(
            ReviewKey(docset_id="vendor-payments", candidate_run_id="missing"), _draft(snapshot)
        )
    with pytest.raises(ReviewInputError, match="docset"):
        ReviewWorkflow(tmp_path).open_review(
            ReviewRequest(docset_id="missing-docset", run_dir=run)
        )


def test_artifact_digests_rejects_missing_and_non_file_required_artifacts(tmp_path: Path) -> None:
    missing_run = _run(tmp_path, "20260723T120000.000000Z")
    (missing_run / "openapi.yaml").unlink()
    with pytest.raises(ReviewInputError, match="required review artifact missing"):
        artifact_digests(missing_run)

    non_file_run = _run(tmp_path, "20260724T120000.000000Z")
    (non_file_run / "openapi.yaml").unlink()
    (non_file_run / "openapi.yaml").mkdir()
    with pytest.raises(ReviewInputError, match="not a file"):
        artifact_digests(non_file_run)
