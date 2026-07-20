from __future__ import annotations

import pytest

from loop_apidoc.core.lifecycle import InvalidTransition, LifecycleMachine
from loop_apidoc.core.models import Actor, ActorKind, LifecycleState, WorkflowRecord


def _actor(kind: ActorKind) -> Actor:
    return Actor(id=f"{kind.value}-1", kind=kind)


def test_publish_cannot_skip_approval():
    machine = LifecycleMachine()
    record = WorkflowRecord(source_set_id="sources", state=LifecycleState.VALIDATED)

    with pytest.raises(InvalidTransition):
        machine.transition(
            record,
            LifecycleState.PUBLISHED,
            actor=_actor(ActorKind.PUBLISHER),
            idempotency_key="publish-1",
        )


def test_runtime_cannot_approve_and_transitions_are_idempotent():
    machine = LifecycleMachine()
    ready = WorkflowRecord(
        source_set_id="sources",
        state=LifecycleState.APPROVAL_READY,
        artifacts=frozenset({"validation_decision", "candidate_release"}),
    )
    with pytest.raises(InvalidTransition):
        machine.transition(
            ready,
            LifecycleState.APPROVED,
            actor=_actor(ActorKind.RUNTIME),
            idempotency_key="approve-runtime",
        )

    approved, event = machine.transition(
        ready,
        LifecycleState.APPROVED,
        actor=_actor(ActorKind.APPROVER),
        idempotency_key="approve-1",
    )
    repeated, repeated_event = machine.transition(
        approved,
        LifecycleState.APPROVED,
        actor=_actor(ActorKind.APPROVER),
        idempotency_key="approve-1",
    )
    assert event is not None
    assert repeated == approved
    assert repeated_event is None
