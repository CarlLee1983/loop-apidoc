from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier

import pytest

from loop_apidoc.core.conformance import ContractConformance, canonical_digest
from loop_apidoc.core.governance import contract_digest
from loop_apidoc.domain.conformance import CompatibilityAmendment, NormativeBaseBinding
from loop_apidoc.feedback.loader import FeedbackInputError, load_current_scope_amendments
from loop_apidoc.foundry import descriptor_io, feedback, paths, query, store
from loop_apidoc.foundry.models import AssetStatus, EffectiveProvenance, FoundryInputError
from tests.foundry.test_feedback import (
    _LATER,
    _amendment,
    _assessment,
    _bundle,
    _contract,
    _decision,
    _effective,
    _proposal,
    _publish_normative_base,
    _release,
    _scope,
    _setup_base,
)


def test_feedback_case_post_publish_failure_removes_owned_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    original_publish = store.publish_asset

    def publish_then_fail(*args: object, **kwargs: object) -> object:
        original_publish(*args, **kwargs)
        raise OSError("injected post-publish failure")

    monkeypatch.setattr(store, "publish_asset", publish_then_fail)

    with pytest.raises(OSError, match="post-publish failure"):
        feedback.persist_feedback_case(
            tmp_path, "payments", bundle, assessment, proposal
        )

    assert not paths.feedback_case_dir(tmp_path, "payments", assessment.assessment_id).exists()
    assert not (paths.docset_dir(tmp_path, "payments") / ".governance.lock").exists()
    assert not (tmp_path / ".foundry/api/.catalog-governance.lock").exists()


def test_feedback_review_post_write_failure_removes_owned_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decision = _decision(case, proposal)
    original_write = descriptor_io.write_once_model_relative

    def write_then_fail(*args: object, **kwargs: object) -> object:
        original_write(*args, **kwargs)
        raise OSError("injected post-write failure")

    monkeypatch.setattr(descriptor_io, "write_once_model_relative", write_then_fail)

    with pytest.raises(OSError, match="post-write failure"):
        feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)

    decision_path = paths.feedback_case_dir(
        tmp_path, "payments", case.case_id
    ) / "review/decision.json"
    assert not decision_path.exists()
    assert not (paths.docset_dir(tmp_path, "payments") / ".governance.lock").exists()
    assert not (tmp_path / ".foundry/api/.catalog-governance.lock").exists()


def test_review_write_once_is_atomic_across_concurrent_writers(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decisions = tuple(
        _decision(case, proposal, approver=f"reviewer-{index}").model_copy(
            update={"rationale": f"review-{index}-" + "x" * 10_000_000}
        )
        for index in range(8)
    )
    barrier = Barrier(len(decisions))

    def record(decision):
        barrier.wait()
        try:
            feedback.record_feedback_review(
                tmp_path, "payments", case.case_id, decision
            )
        except FoundryInputError:
            return "rejected"
        except BaseException as exc:  # pragma: no cover - diagnostic failure result
            return type(exc).__name__
        return "written"

    with ThreadPoolExecutor(max_workers=len(decisions)) as executor:
        outcomes = tuple(executor.map(record, decisions))

    assert outcomes.count("written") == 1
    assert outcomes.count("rejected") == len(decisions) - 1


def test_current_rejects_tampered_amendment_artifact(tmp_path: Path) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decision = _decision(case, proposal)
    feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)
    amendment = _amendment(proposal, decision)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    amendment_path = (
        tmp_path
        / ".foundry/api/docsets/payments/effective/scopes"
        / asset.scope_digest
        / "assets"
        / asset.effective_asset_id
        / asset.artifacts.compatibility_amendment
    )
    stored = CompatibilityAmendment.model_validate_json(amendment_path.read_bytes())
    amendment_path.write_text(
        stored.model_copy(update={"amendment_id": "tampered"}).model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(FoundryInputError, match="amendment artifact digest is stale"):
        query.load_current_effective_asset(
            tmp_path, "payments", _scope(), now=_LATER
        )


@pytest.mark.parametrize("tamper", ["nonapproved_status", "unknown_metadata"])
def test_current_rejects_semantically_invalid_effective_asset(
    tmp_path: Path, tamper: str
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decision = _decision(case, proposal)
    feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)
    amendment = _amendment(proposal, decision)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    asset_path = (
        tmp_path
        / ".foundry/api/docsets/payments/effective/scopes"
        / asset.scope_digest
        / "assets"
        / asset.effective_asset_id
        / "asset.json"
    )
    expected = "[Ee]xtra inputs are not permitted"
    if tamper == "nonapproved_status":
        candidate = asset.model_copy(update={"status": AssetStatus.CANDIDATE})
        asset_path.write_text(candidate.model_dump_json(), encoding="utf-8")
        pointer = store.load_effective_current(
            tmp_path, "payments", asset.scope_digest
        )
        assert pointer is not None
        store.save_effective_current(
            tmp_path,
            "payments",
            asset.scope_digest,
            pointer.model_copy(
                update={"effective_asset_digest": canonical_digest(candidate)}
            ),
        )
        expected = "not approved"
    else:
        payload = json.loads(asset_path.read_text(encoding="utf-8"))
        payload["untrusted_metadata"] = "secret-bearing attacker field"
        asset_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FoundryInputError, match=expected):
        query.load_current_effective_asset(
            tmp_path, "payments", _scope(), now=_LATER
        )


def test_current_rejects_rehashed_provenance_that_disagrees_with_approval(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decision = _decision(case, proposal)
    feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)
    amendment = _amendment(proposal, decision)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    asset_dir = (
        tmp_path
        / ".foundry/api/docsets/payments/effective/scopes"
        / asset.scope_digest
        / "assets"
        / asset.effective_asset_id
    )
    provenance_path = asset_dir / asset.artifacts.provenance
    provenance = EffectiveProvenance.model_validate_json(
        provenance_path.read_bytes()
    ).model_copy(update={"approval_id": "forged-approval"})
    provenance_path.write_text(provenance.model_dump_json(), encoding="utf-8")
    forged_asset = asset.model_copy(
        update={"provenance_digest": canonical_digest(provenance)}
    )
    (asset_dir / "asset.json").write_text(
        forged_asset.model_dump_json(), encoding="utf-8"
    )
    pointer = store.load_effective_current(
        tmp_path, "payments", asset.scope_digest
    )
    assert pointer is not None
    store.save_effective_current(
        tmp_path,
        "payments",
        asset.scope_digest,
        pointer.model_copy(
            update={
                "effective_asset_digest": canonical_digest(forged_asset),
                "provenance_digest": forged_asset.provenance_digest,
            }
        ),
    )

    with pytest.raises(FoundryInputError, match="provenance approval lineage"):
        query.load_current_effective_asset(
            tmp_path, "payments", _scope(), now=_LATER
        )


def test_effective_release_supersedes_only_exact_scope_without_mutating_prior_bytes(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decision = _decision(case, proposal)
    feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)
    amendment = _amendment(proposal, decision)
    first = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    first_dir = (
        tmp_path
        / ".foundry/api/docsets/payments/effective/scopes"
        / first.scope_digest
        / "assets"
        / first.effective_asset_id
    )
    prior_bytes = {
        path.relative_to(first_dir): path.read_bytes()
        for path in first_dir.rglob("*")
        if path.is_file()
    }

    second = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment, at=_LATER + timedelta(minutes=1)),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )

    assert second.supersedes == first.effective_asset_id
    assert (
        query.load_current_effective_asset(
            tmp_path,
            "payments",
            _scope(),
            now=_LATER + timedelta(minutes=1),
        ).effective_asset_id
        == second.effective_asset_id
    )
    assert {
        path.relative_to(first_dir): path.read_bytes()
        for path in first_dir.rglob("*")
        if path.is_file()
    } == prior_bytes
    assert store.load_current(tmp_path, "payments").current_asset == "payments-base"
    assert load_current_scope_amendments(
        tmp_path, "payments", _scope()
    ) == (amendment,)

    current = store.load_effective_current(
        tmp_path, "payments", second.scope_digest
    )
    assert current is not None
    store.save_effective_current(
        tmp_path,
        "payments",
        second.scope_digest,
        current.model_copy(update={"current_asset": first.effective_asset_id}),
    )
    forged_successor = _effective(
        amendment, at=_LATER + timedelta(minutes=2)
    )
    with pytest.raises(FoundryInputError, match="current asset digest is stale"):
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            case.case_id,
            amendment,
            forged_successor,
            release=_release(amendment),
            composition_amendments=(amendment,),
        )


def test_new_reviewed_amendment_can_replace_expired_current_lineage(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    first_bundle = _bundle()
    first_assessment = _assessment(first_bundle)
    first_proposal = _proposal(first_bundle, first_assessment)
    first_case = feedback.persist_feedback_case(
        tmp_path, "payments", first_bundle, first_assessment, first_proposal
    )
    first_decision = _decision(
        first_case,
        first_proposal,
        expires_at=_LATER + timedelta(minutes=1),
    )
    feedback.record_feedback_review(
        tmp_path, "payments", first_case.case_id, first_decision
    )
    first_amendment = _amendment(first_proposal, first_decision)
    first = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        first_case.case_id,
        first_amendment,
        _effective(first_amendment),
        release=_release(first_amendment),
        composition_amendments=(first_amendment,),
    )

    second_time = _LATER + timedelta(minutes=2)
    second_bundle = _bundle(suffix="2")
    second_assessment = _assessment(second_bundle)
    second_proposal = _proposal(
        second_bundle,
        second_assessment,
        created_at=second_time,
    )
    second_case = feedback.persist_feedback_case(
        tmp_path, "payments", second_bundle, second_assessment, second_proposal
    )
    second_decision = _decision(
        second_case, second_proposal, decided_at=second_time
    )
    feedback.record_feedback_review(
        tmp_path, "payments", second_case.case_id, second_decision
    )
    second_amendment = _amendment(
        second_proposal, second_decision, amendment_id="amendment-2"
    ).model_copy(update={"supersedes": first_amendment.amendment_id})
    effective = ContractConformance().compose(
        _release(second_amendment),
        (first_amendment, second_amendment),
        target=_scope(),
        now=second_time,
    )

    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        second_case.case_id,
        second_amendment,
        effective,
        release=_release(second_amendment),
        composition_amendments=(first_amendment, second_amendment),
    )

    assert asset.applied_amendment_ids == ("amendment-2",)
    assert asset.open_discrepancy_count > 0
    assert query.load_current_effective_asset(
        tmp_path, "payments", _scope(), now=second_time
    ) == asset

    first_asset_path = (
        tmp_path
        / ".foundry/api/docsets/payments/effective/scopes"
        / first.scope_digest
        / "assets"
        / first.effective_asset_id
        / "asset.json"
    )
    first_asset_payload = json.loads(first_asset_path.read_text(encoding="utf-8"))
    first_asset_payload["approved_by"] = {"id": "forged", "version": "1"}
    first_asset_path.write_text(
        json.dumps(first_asset_payload),
        encoding="utf-8",
    )
    with pytest.raises(FeedbackInputError, match="predecessor asset digest"):
        load_current_scope_amendments(tmp_path, "payments", _scope())
    with pytest.raises(FoundryInputError, match="predecessor asset digest"):
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            second_case.case_id,
            second_amendment,
            ContractConformance().compose(
                _release(second_amendment),
                (first_amendment, second_amendment),
                target=_scope(),
                now=second_time + timedelta(minutes=1),
            ),
            release=_release(second_amendment),
            composition_amendments=(first_amendment, second_amendment),
        )


def test_normative_drift_surfaces_stale_amendment_count_in_current_asset(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    first_bundle = _bundle()
    first_assessment = _assessment(first_bundle)
    first_proposal = _proposal(first_bundle, first_assessment)
    first_case = feedback.persist_feedback_case(
        tmp_path, "payments", first_bundle, first_assessment, first_proposal
    )
    first_decision = _decision(first_case, first_proposal)
    feedback.record_feedback_review(
        tmp_path, "payments", first_case.case_id, first_decision
    )
    first_amendment = _amendment(first_proposal, first_decision)
    feedback.approve_feedback_case(
        tmp_path,
        "payments",
        first_case.case_id,
        first_amendment,
        _effective(first_amendment),
        release=_release(first_amendment),
        composition_amendments=(first_amendment,),
    )

    _publish_normative_base(tmp_path, "payments-base-2", run_id="base-run-2")
    second_time = _LATER + timedelta(minutes=2)
    second_base = NormativeBaseBinding(
        docset_id="payments",
        asset_id="payments-base-2",
        contract_digest=contract_digest(_contract()),
    )
    second_bundle = _bundle(suffix="2").model_copy(
        update={"base": second_base}
    )
    second_assessment = _assessment(second_bundle)
    second_proposal = _proposal(
        second_bundle,
        second_assessment,
        created_at=second_time,
    )
    second_case = feedback.persist_feedback_case(
        tmp_path, "payments", second_bundle, second_assessment, second_proposal
    )
    second_decision = _decision(
        second_case, second_proposal, decided_at=second_time
    )
    feedback.record_feedback_review(
        tmp_path, "payments", second_case.case_id, second_decision
    )
    second_amendment = _amendment(
        second_proposal, second_decision, amendment_id="amendment-2"
    )
    second_release = _release(second_amendment)
    effective = ContractConformance().compose(
        second_release,
        (first_amendment, second_amendment),
        target=_scope(),
        now=second_time,
    )

    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        second_case.case_id,
        second_amendment,
        effective,
        release=second_release,
        composition_amendments=(first_amendment, second_amendment),
    )

    assert effective.stale_amendment_ids == ("amendment-1",)
    assert asset.stale_amendment_count == 1
    assert query.load_current_effective_asset(
        tmp_path, "payments", _scope(), now=second_time
    ).stale_amendment_count == 1
