from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event

import pytest

from loop_apidoc.adapters.memory import (
    FixedClock,
    InMemoryArtifactSink,
    InMemoryCoreUnitOfWork,
    StaticApprovalAdapter,
    StaticSourceAdapter,
)
from loop_apidoc.adapters.runtime import CallableRuntimeAdapter
from loop_apidoc.core.governance import ApprovalRejected
from loop_apidoc.core.lifecycle import InvalidTransition
from loop_apidoc.core.persistence import CommandInProgressError, ConcurrentCommitError
from loop_apidoc.core.models import (
    Actor,
    ActorKind,
    ApprovalDecision,
    ClaimProposal,
    EvidenceBundle,
    LifecycleState,
    EvidenceFragment,
    ReleaseStatus,
    RuntimeResult,
    SourceArtifact,
    SourceDescriptor,
    SourceSet,
)
from loop_apidoc.core.service import EvidenceToContractService
from loop_apidoc.domain.claim_paths import claim_value_at, material_claim_paths
from loop_apidoc.domain.evidence import (
    ClaimSupportProposal,
    FragmentPrecision,
    LineRangeLocator,
    SupportRelationshipType,
    VerificationMethod,
    canonical_json,
    fragment_digest,
)
from loop_apidoc.domain.models import ContractMetadata
from loop_apidoc.domain.projections import OpenApiProjectionCompiler
from loop_apidoc.domain.rules import ApiDomainRulePack


NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)
_SOURCE_SET_ID = "sources"


def _operation(name: str = "health") -> dict[str, object]:
    return {
        "method": "GET",
        "path": f"/{name}",
        "responses": [{"status_code": "200", "description": "OK"}],
    }


def _source_set() -> SourceSet:
    return SourceSet(
        id=_SOURCE_SET_ID,
        version="1",
        sources=(SourceDescriptor(id="manual", kind="memory", locator="manual"),),
    )


def _bundle(operation: dict[str, object]) -> EvidenceBundle:
    paths = material_claim_paths("operation", operation)
    return EvidenceBundle(
        source_set_id=_SOURCE_SET_ID,
        source_set_version="1",
        artifacts=(
            SourceArtifact(
                id="artifact-1",
                source_id="manual",
                media_type="text/markdown",
                content_digest="a" * 64,
                acquired_at=NOW,
            ),
        ),
        fragments=tuple(
            EvidenceFragment(
                id=f"fragment-{index}",
                source_artifact_id="artifact-1",
                locator=LineRangeLocator(start_line=index + 1, end_line=index + 1),
                fragment_digest=fragment_digest(
                    canonical_json(claim_value_at("operation", operation, path))
                ),
                normalized_excerpt=canonical_json(
                    claim_value_at("operation", operation, path)
                ),
                semantic_value=claim_value_at("operation", operation, path),
                semantic_role="field.value",
                precision=FragmentPrecision.EXACT,
            )
            for index, path in enumerate(paths)
        ),
    )


def _runtime_result(operation: dict[str, object], identity: str = "parser") -> RuntimeResult:
    paths = material_claim_paths("operation", operation)
    return RuntimeResult(
        claim_proposals=(
            ClaimProposal(
                id=f"proposal-{operation['path']}",
                claim_kind="operation",
                subject=f"GET {operation['path']}",
                predicate="definition",
                value=operation,
                support_proposals=tuple(
                    ClaimSupportProposal(
                        fragment_id=f"fragment-{index}",
                        claim_path=path,
                        proposed_relationship=(
                            SupportRelationshipType.EXPLICIT_SUPPORT
                        ),
                        verification_method=(
                            VerificationMethod.EXACT_NORMALIZED_VALUE
                        ),
                    )
                    for index, path in enumerate(paths)
                ),
                runtime_identity=identity,
            ),
        ),
        runtime_identity=identity,
        runtime_version="1",
    )


def _service(
    runtime_results: list[RuntimeResult],
) -> tuple[
    EvidenceToContractService,
    InMemoryCoreUnitOfWork,
    InMemoryArtifactSink,
    list[object],
]:
    operation = _operation()
    source_bundle = _bundle(operation)
    uow = InMemoryCoreUnitOfWork()
    artifacts = InMemoryArtifactSink()
    runtime_calls: list[object] = []

    def propose(work_item: object) -> RuntimeResult:
        runtime_calls.append(work_item)
        return runtime_results[len(runtime_calls) - 1]

    approval = ApprovalDecision(
        approved=True,
        actor=Actor(id="reviewer", kind=ActorKind.APPROVER),
        decided_at=NOW,
    )
    service = EvidenceToContractService(
        source=StaticSourceAdapter(source_bundle),
        runtime=CallableRuntimeAdapter("parser", "1", propose),
        unit_of_work=uow,
        artifact_sink=artifacts,
        approval=StaticApprovalAdapter(approval),
        clock=FixedClock(NOW),
        domain_rules=ApiDomainRulePack(version="1"),
    )
    return service, uow, artifacts, runtime_calls


def _advance_to_contract(
    service: EvidenceToContractService,
) -> None:
    service.register_source_set(_source_set())
    service.acquire(_SOURCE_SET_ID)
    service.request_claim_proposals(_SOURCE_SET_ID, ("operation",))
    service.reconcile(_SOURCE_SET_ID)
    service.build_contract(
        _SOURCE_SET_ID,
        ContractMetadata(
            contract_id="health",
            title="Health API",
            version="1",
            source_set_id=_SOURCE_SET_ID,
            source_set_version="1",
            domain_version="1",
        ),
    )


def _advance_to_approved(service: EvidenceToContractService) -> None:
    _advance_to_contract(service)
    service.validate(_SOURCE_SET_ID, (OpenApiProjectionCompiler(version="1"),))
    service.approve(_SOURCE_SET_ID)


def test_invalid_order_never_calls_external_ports() -> None:
    service, uow, artifacts, runtime_calls = _service([_runtime_result(_operation())])
    service.register_source_set(_source_set())

    with pytest.raises(InvalidTransition):
        service.request_claim_proposals(_SOURCE_SET_ID, ("operation",))
    with pytest.raises(InvalidTransition):
        service.approve(_SOURCE_SET_ID)
    with pytest.raises((ApprovalRejected, InvalidTransition)):
        service.publish(_SOURCE_SET_ID)

    assert runtime_calls == []
    assert artifacts.publications == {}
    assert service.approval_port.requests == 0
    assert [event.kind for event in uow.events] == ["lifecycle.registered"]


def test_exact_proposal_retry_keeps_first_result_and_does_not_reinvoke_runtime() -> None:
    first = _runtime_result(_operation("health"))
    second = _runtime_result(_operation("different"))
    service, uow, _artifacts, runtime_calls = _service([first, second])
    service.register_source_set(_source_set())
    service.acquire(_SOURCE_SET_ID)

    service.request_claim_proposals(_SOURCE_SET_ID, ("operation",))
    service.request_claim_proposals(_SOURCE_SET_ID, ("operation",))

    snapshot = uow.load(_SOURCE_SET_ID)
    assert snapshot is not None
    assert snapshot.runtime_result == first
    assert len(runtime_calls) == 1
    assert [event.kind for event in uow.events] == [
        "lifecycle.registered",
        "lifecycle.acquired",
        "lifecycle.claims_proposed",
    ]

    with pytest.raises(InvalidTransition):
        service.request_claim_proposals(_SOURCE_SET_ID, ("schema",))
    assert len(runtime_calls) == 1


def test_reconcile_build_and_validate_retries_replay_durable_results() -> None:
    service, uow, _artifacts, _runtime_calls = _service([_runtime_result(_operation())])
    service.register_source_set(_source_set())
    service.acquire(_SOURCE_SET_ID)
    service.request_claim_proposals(_SOURCE_SET_ID, ("operation",))

    service.reconcile(_SOURCE_SET_ID)
    reconciled = uow.load(_SOURCE_SET_ID)
    service.reconcile(_SOURCE_SET_ID)
    assert uow.load(_SOURCE_SET_ID) == reconciled
    assert [event.kind for event in uow.events].count("lifecycle.reconciled") == 1

    metadata = ContractMetadata(
        contract_id="health",
        title="Health API",
        version="1",
        source_set_id=_SOURCE_SET_ID,
        source_set_version="1",
        domain_version="1",
    )
    service.build_contract(_SOURCE_SET_ID, metadata)
    built = uow.load(_SOURCE_SET_ID)
    service.build_contract(_SOURCE_SET_ID, metadata)
    assert uow.load(_SOURCE_SET_ID) == built
    assert [event.kind for event in uow.events].count("lifecycle.contract_built") == 1

    compilers = (OpenApiProjectionCompiler(version="1"),)
    decision = service.validate(_SOURCE_SET_ID, compilers)
    assert service.validate(_SOURCE_SET_ID, compilers) == decision
    assert [event.kind for event in uow.events].count("lifecycle.validated") == 1
    assert [event.kind for event in uow.events].count("lifecycle.approval_ready") == 1


def test_failed_reconcile_releases_reservation_for_normal_proposal_sequence() -> None:
    service, uow, _artifacts, _runtime_calls = _service([_runtime_result(_operation())])
    service.register_source_set(_source_set())
    service.acquire(_SOURCE_SET_ID)

    with pytest.raises(InvalidTransition):
        service.reconcile(_SOURCE_SET_ID)

    service.request_claim_proposals(_SOURCE_SET_ID, ("operation",))
    service.reconcile(_SOURCE_SET_ID)

    snapshot = uow.load(_SOURCE_SET_ID)
    assert snapshot is not None
    assert snapshot.workflow.state is LifecycleState.RECONCILED
    assert [event.kind for event in uow.events].count("lifecycle.reconciled") == 1


def test_failed_build_releases_reservation_for_reconciled_contract() -> None:
    service, uow, _artifacts, _runtime_calls = _service([_runtime_result(_operation())])
    metadata = ContractMetadata(
        contract_id="health",
        title="Health API",
        version="1",
        source_set_id=_SOURCE_SET_ID,
        source_set_version="1",
        domain_version="1",
    )
    service.register_source_set(_source_set())
    service.acquire(_SOURCE_SET_ID)
    service.request_claim_proposals(_SOURCE_SET_ID, ("operation",))

    with pytest.raises(InvalidTransition):
        service.build_contract(_SOURCE_SET_ID, metadata)

    service.reconcile(_SOURCE_SET_ID)
    service.build_contract(_SOURCE_SET_ID, metadata)

    snapshot = uow.load(_SOURCE_SET_ID)
    assert snapshot is not None
    assert snapshot.workflow.state is LifecycleState.CONTRACT_BUILT
    assert [event.kind for event in uow.events].count("lifecycle.contract_built") == 1


def test_register_retry_replays_its_original_workflow_after_later_transition() -> None:
    service, _uow, _artifacts, _runtime_calls = _service([_runtime_result(_operation())])

    registered = service.register_source_set(_source_set())
    service.acquire(_SOURCE_SET_ID)

    assert service.register_source_set(_source_set()) == registered
    assert registered.state is LifecycleState.REGISTERED


def test_conflicting_registration_releases_reservation_and_acquire_replays() -> None:
    service, uow, _artifacts, _runtime_calls = _service([_runtime_result(_operation())])
    service.register_source_set(_source_set())

    conflicting = _source_set().model_copy(update={"version": "2"})
    with pytest.raises(ConcurrentCommitError, match="already registered"):
        service.register_source_set(conflicting)

    # The rejected registration used a different idempotency key. Its reservation
    # must be released, or it would fence the valid acquire command indefinitely.
    service.acquire(_SOURCE_SET_ID)
    service.acquire(_SOURCE_SET_ID)

    snapshot = uow.load(_SOURCE_SET_ID)
    assert snapshot is not None
    assert snapshot.workflow.state is LifecycleState.ACQUIRED
    assert [event.kind for event in uow.events] == [
        "lifecycle.registered",
        "lifecycle.acquired",
    ]


def test_concurrent_same_proposal_reserves_before_runtime_effect() -> None:
    first = _runtime_result(_operation("health"))
    second = _runtime_result(_operation("different"))
    service, _uow, _artifacts, runtime_calls = _service([first, second])
    service.register_source_set(_source_set())
    service.acquire(_SOURCE_SET_ID)

    entered = Event()
    release_first = Event()

    def propose(work_item: object) -> RuntimeResult:
        runtime_calls.append(work_item)
        if len(runtime_calls) == 1:
            entered.set()
            assert release_first.wait(timeout=5)
            return first
        return second

    service.runtime = CallableRuntimeAdapter("parser", "1", propose)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first_call = executor.submit(
            service.request_claim_proposals,
            _SOURCE_SET_ID,
            ("operation",),
        )
        assert entered.wait(timeout=5)
        try:
            with pytest.raises(CommandInProgressError, match="in progress"):
                service.request_claim_proposals(_SOURCE_SET_ID, ("operation",))
            with pytest.raises(CommandInProgressError, match="in progress"):
                service.request_claim_proposals(_SOURCE_SET_ID, ("schema",))
            assert len(runtime_calls) == 1
        finally:
            release_first.set()
        first_call.result(timeout=5)

    service.request_claim_proposals(_SOURCE_SET_ID, ("operation",))
    assert len(runtime_calls) == 1


def test_lost_commit_acknowledgement_does_not_repeat_runtime_on_retry() -> None:
    first = _runtime_result(_operation("health"))
    service, uow, _artifacts, runtime_calls = _service([first])
    service.register_source_set(_source_set())
    service.acquire(_SOURCE_SET_ID)

    uow.lose_next_commit_acknowledgement()
    with pytest.raises(RuntimeError, match="acknowledgement"):
        service.request_claim_proposals(_SOURCE_SET_ID, ("operation",))

    committed = uow.load(_SOURCE_SET_ID)
    assert committed is not None
    assert committed.runtime_result == first
    assert len(runtime_calls) == 1

    service.request_claim_proposals(_SOURCE_SET_ID, ("operation",))
    assert len(runtime_calls) == 1
    assert [event.kind for event in uow.events].count("lifecycle.claims_proposed") == 1


def test_unknown_source_set_failure_releases_reservation_for_registration() -> None:
    service, uow, _artifacts, _runtime_calls = _service([_runtime_result(_operation())])

    with pytest.raises(ValueError, match="not registered"):
        service.acquire(_SOURCE_SET_ID)

    service.register_source_set(_source_set())
    service.acquire(_SOURCE_SET_ID)

    snapshot = uow.load(_SOURCE_SET_ID)
    assert snapshot is not None
    assert snapshot.workflow.state is LifecycleState.ACQUIRED
    assert [event.kind for event in uow.events] == [
        "lifecycle.registered",
        "lifecycle.acquired",
    ]


def test_known_rejected_approval_releases_the_command_reservation() -> None:
    service, _uow, _artifacts, _runtime_calls = _service([_runtime_result(_operation())])
    _advance_to_contract(service)
    service.validate(_SOURCE_SET_ID, (OpenApiProjectionCompiler(version="1"),))
    service.approval_port = StaticApprovalAdapter(
        ApprovalDecision(
            approved=False,
            actor=Actor(id="reviewer", kind=ActorKind.APPROVER),
            decided_at=NOW,
        )
    )

    with pytest.raises(ApprovalRejected):
        service.approve(_SOURCE_SET_ID)

    service.approval_port = StaticApprovalAdapter(
        ApprovalDecision(
            approved=True,
            actor=Actor(id="reviewer", kind=ActorKind.APPROVER),
            decided_at=NOW,
        )
    )
    assert service.approve(_SOURCE_SET_ID).status is ReleaseStatus.APPROVED


def test_approval_retry_replays_approved_release_after_publication() -> None:
    service, _uow, _artifacts, _runtime_calls = _service([_runtime_result(_operation())])
    _advance_to_approved(service)

    published = service.publish(_SOURCE_SET_ID)
    replayed_approval = service.approve(_SOURCE_SET_ID)

    assert published.status is ReleaseStatus.PUBLISHED
    assert replayed_approval.status is ReleaseStatus.APPROVED


def test_publish_retry_replays_the_committed_release_without_duplicate_event() -> None:
    service, uow, artifacts, _runtime_calls = _service([_runtime_result(_operation())])
    _advance_to_approved(service)

    published = service.publish(_SOURCE_SET_ID)
    replayed = service.publish(_SOURCE_SET_ID)

    assert replayed == published
    assert [event.kind for event in uow.events].count("lifecycle.published") == 1
    assert len(artifacts.publications) == 1


def test_unapproved_publish_never_creates_artifacts() -> None:
    service, _uow, artifacts, _runtime_calls = _service([_runtime_result(_operation())])
    _advance_to_contract(service)
    service.validate(_SOURCE_SET_ID, (OpenApiProjectionCompiler(version="1"),))

    with pytest.raises((ApprovalRejected, InvalidTransition)):
        service.publish(_SOURCE_SET_ID)

    assert artifacts.publications == {}


def test_artifact_sink_failure_after_content_write_leaves_approved_state_for_retry() -> None:
    service, uow, artifacts, _runtime_calls = _service([_runtime_result(_operation())])
    _advance_to_approved(service)

    class FailsOnceAfterWriting:
        def __init__(self) -> None:
            self.fail = True

        def publish(self, release, projections):
            refs = artifacts.publish(release, projections)
            if self.fail:
                self.fail = False
                raise RuntimeError("artifact sink interrupted after content write")
            return refs

    service.artifact_sink = FailsOnceAfterWriting()
    with pytest.raises(RuntimeError, match="artifact sink"):
        service.publish(_SOURCE_SET_ID)

    failed = uow.load(_SOURCE_SET_ID)
    assert failed is not None
    assert failed.release is not None
    assert failed.release.status is ReleaseStatus.APPROVED
    assert failed.current is None
    assert len(artifacts.publications) == 1

    published = service.publish(_SOURCE_SET_ID)
    assert published.status is ReleaseStatus.PUBLISHED
    assert len(artifacts.publications) == 1


@pytest.mark.parametrize("boundary", ("payload", "workflow", "current", "event"))
def test_publication_commit_fault_leaves_approved_snapshot_and_retry_converges(
    boundary: str,
) -> None:
    service, uow, artifacts, _runtime_calls = _service([_runtime_result(_operation())])
    _advance_to_approved(service)
    before = uow.load(_SOURCE_SET_ID)
    assert before is not None
    assert before.release is not None
    assert before.release.status is ReleaseStatus.APPROVED

    uow.fail_next_commit_at(boundary)
    with pytest.raises(RuntimeError, match=boundary):
        service.publish(_SOURCE_SET_ID)

    assert uow.load(_SOURCE_SET_ID) == before
    assert all(event.kind != "lifecycle.published" for event in uow.events)
    assert len(artifacts.publications) == 1

    published = service.publish(_SOURCE_SET_ID)
    after = uow.load(_SOURCE_SET_ID)
    assert published.status is ReleaseStatus.PUBLISHED
    assert after is not None
    assert after.current is not None
    assert after.current.release_id == published.release_id
    assert [event.kind for event in uow.events].count("lifecycle.published") == 1
    assert len(artifacts.publications) == 1


def test_validation_commit_fault_leaves_no_partial_candidate_or_projections() -> None:
    service, uow, _artifacts, _runtime_calls = _service([_runtime_result(_operation())])
    _advance_to_contract(service)
    before = uow.load(_SOURCE_SET_ID)
    assert before is not None

    uow.fail_next_commit_at("event")
    with pytest.raises(RuntimeError, match="event"):
        service.validate(_SOURCE_SET_ID, (OpenApiProjectionCompiler(version="1"),))

    assert uow.load(_SOURCE_SET_ID) == before
    assert before.validation_decision is None
    assert before.projections is None
    assert before.release is None

    decision = service.validate(_SOURCE_SET_ID, (OpenApiProjectionCompiler(version="1"),))
    after = uow.load(_SOURCE_SET_ID)
    assert decision.verdict.value == "accept"
    assert after is not None
    assert after.release is not None
    assert after.projections is not None
    assert after.workflow.state.value == "approval_ready"
