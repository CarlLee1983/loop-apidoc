from __future__ import annotations

import hashlib

from loop_apidoc.core.models import (
    Actor,
    ActorKind,
    DomainEvent,
    LifecycleState,
    WorkflowRecord,
)


class InvalidTransition(ValueError):
    """The lifecycle graph, artifacts, or actor do not permit a transition."""


_ALLOWED = {
    LifecycleState.REGISTERED: {LifecycleState.ACQUIRED},
    LifecycleState.ACQUIRED: {LifecycleState.CLAIMS_PROPOSED},
    LifecycleState.CLAIMS_PROPOSED: {LifecycleState.RECONCILED},
    LifecycleState.RECONCILED: {LifecycleState.CONTRACT_BUILT},
    LifecycleState.CONTRACT_BUILT: {LifecycleState.VALIDATED},
    LifecycleState.VALIDATED: {
        LifecycleState.REVIEW_REQUIRED,
        LifecycleState.APPROVAL_READY,
    },
    LifecycleState.REVIEW_REQUIRED: {LifecycleState.APPROVED, LifecycleState.REVOKED},
    LifecycleState.APPROVAL_READY: {LifecycleState.APPROVED, LifecycleState.REVOKED},
    LifecycleState.APPROVED: {LifecycleState.PUBLISHED, LifecycleState.REVOKED},
    LifecycleState.PUBLISHED: {
        LifecycleState.STALE,
        LifecycleState.SUPERSEDED,
        LifecycleState.REVOKED,
    },
    LifecycleState.STALE: {LifecycleState.SUPERSEDED, LifecycleState.REVOKED},
}
_REQUIRED = {
    LifecycleState.ACQUIRED: {"evidence_bundle"},
    LifecycleState.CLAIMS_PROPOSED: {"runtime_result"},
    LifecycleState.RECONCILED: {"grounded_claims"},
    LifecycleState.CONTRACT_BUILT: {"contract"},
    LifecycleState.VALIDATED: {"validation_decision"},
    LifecycleState.REVIEW_REQUIRED: {"validation_decision", "candidate_release"},
    LifecycleState.APPROVAL_READY: {"validation_decision", "candidate_release"},
    LifecycleState.APPROVED: {"candidate_release", "validation_decision"},
    LifecycleState.PUBLISHED: {"projections"},
}
_ACTORS = {
    LifecycleState.CLAIMS_PROPOSED: {ActorKind.RUNTIME, ActorKind.SYSTEM},
    LifecycleState.VALIDATED: {ActorKind.POLICY, ActorKind.SYSTEM},
    LifecycleState.REVIEW_REQUIRED: {ActorKind.POLICY, ActorKind.SYSTEM},
    LifecycleState.APPROVAL_READY: {ActorKind.POLICY, ActorKind.SYSTEM},
    LifecycleState.APPROVED: {ActorKind.APPROVER},
    LifecycleState.PUBLISHED: {ActorKind.PUBLISHER, ActorKind.SYSTEM},
}


class LifecycleMachine:
    def transition(
        self,
        record: WorkflowRecord,
        target: LifecycleState,
        *,
        actor: Actor,
        idempotency_key: str,
        artifacts: frozenset[str] = frozenset(),
    ) -> tuple[WorkflowRecord, DomainEvent | None]:
        if (
            idempotency_key in record.processed_idempotency_keys
            and target is record.state
        ):
            return record, None
        if target not in _ALLOWED.get(record.state, set()):
            raise InvalidTransition(
                f"{record.state.value} cannot transition to {target.value}"
            )
        permitted = _ACTORS.get(target)
        if permitted is not None and actor.kind not in permitted:
            raise InvalidTransition(f"{actor.kind.value} cannot perform {target.value}")
        combined = record.artifacts | artifacts
        missing = _REQUIRED.get(target, set()) - combined
        if missing:
            raise InvalidTransition(
                f"{target.value} requires artifacts: {sorted(missing)}"
            )
        updated = record.model_copy(
            update={
                "state": target,
                "artifacts": combined,
                "processed_idempotency_keys": (
                    record.processed_idempotency_keys | {idempotency_key}
                ),
            }
        )
        event_id = hashlib.sha256(
            f"{record.source_set_id}:{idempotency_key}:{target.value}".encode()
        ).hexdigest()[:20]
        return updated, DomainEvent(
            id=f"event-{event_id}",
            aggregate_id=record.source_set_id,
            kind=f"lifecycle.{target.value}",
            actor=actor,
            correlation_id=idempotency_key,
        )
