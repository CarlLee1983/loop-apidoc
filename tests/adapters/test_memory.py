from __future__ import annotations

import pytest

from loop_apidoc.adapters.memory import InMemoryCoreUnitOfWork
from loop_apidoc.core.models import (
    Actor,
    ActorKind,
    DomainEvent,
    LifecycleState,
    RuntimeResult,
    SourceDescriptor,
    SourceSet,
    WorkflowRecord,
)
from loop_apidoc.core.persistence import (
    CommandInProgressError,
    CoreSnapshot,
    LifecycleCommit,
    ReservationDisposition,
)


_SOURCE_SET = SourceSet(
    id="sources",
    version="1",
    sources=(SourceDescriptor(id="manual", kind="memory", locator="manual"),),
)
_REGISTER_KEY = "sources:register:fixed"


def _snapshot() -> CoreSnapshot:
    return CoreSnapshot(
        source_set=_SOURCE_SET,
        workflow=WorkflowRecord(
            source_set_id="sources",
            state=LifecycleState.REGISTERED,
            artifacts=frozenset({"source_set"}),
            processed_idempotency_keys=frozenset({_REGISTER_KEY}),
        ),
    )


def _event(identifier: str, key: str) -> DomainEvent:
    return DomainEvent(
        id=identifier,
        aggregate_id="sources",
        kind="lifecycle.test",
        actor=Actor(id="test", kind=ActorKind.SYSTEM),
        correlation_id=key,
    )


def _reserve_token(uow: InMemoryCoreUnitOfWork, key: str) -> str:
    reservation = uow.reserve("sources", key)
    assert reservation.disposition is ReservationDisposition.ACQUIRED
    assert reservation.token is not None
    return reservation.token


def test_memory_uow_refuses_to_replace_an_immutable_source_set() -> None:
    uow = InMemoryCoreUnitOfWork()
    initial = _snapshot()
    initial = uow.commit(
        LifecycleCommit(
            source_set_id="sources",
            idempotency_key=_REGISTER_KEY,
            reservation_token=_reserve_token(uow, _REGISTER_KEY),
            updated=initial,
            events=(_event("register", _REGISTER_KEY),),
        )
    ).snapshot
    changed_key = "sources:replace:fixed"
    changed = initial.model_copy(
        update={
            "source_set": _SOURCE_SET.model_copy(update={"sources": ()}),
            "workflow": initial.workflow.model_copy(
                update={
                    "processed_idempotency_keys": (
                        initial.workflow.processed_idempotency_keys | {changed_key}
                    )
                }
            ),
        }
    )

    with pytest.raises(ValueError, match="source sets are immutable"):
        uow.commit(
            LifecycleCommit(
                source_set_id="sources",
                idempotency_key=changed_key,
                reservation_token=_reserve_token(uow, changed_key),
                expected=initial,
                updated=changed,
                events=(_event("replace", changed_key),),
            )
        )


def test_same_operation_reservation_returns_first_runtime_result() -> None:
    uow = InMemoryCoreUnitOfWork()
    initial = _snapshot()
    initial = uow.commit(
        LifecycleCommit(
            source_set_id="sources",
            idempotency_key=_REGISTER_KEY,
            reservation_token=_reserve_token(uow, _REGISTER_KEY),
            updated=initial,
            events=(_event("register", _REGISTER_KEY),),
        )
    ).snapshot
    proposal_key = "sources:propose:fixed"
    workflow = initial.workflow.model_copy(
        update={
            "processed_idempotency_keys": (
                initial.workflow.processed_idempotency_keys | {proposal_key}
            )
        }
    )
    first = initial.model_copy(
        update={
            "runtime_result": RuntimeResult(
                runtime_identity="first",
                runtime_version="1",
            ),
            "workflow": workflow,
        }
    )
    uow.commit(
        LifecycleCommit(
            source_set_id="sources",
            idempotency_key=proposal_key,
            reservation_token=_reserve_token(uow, proposal_key),
            expected=initial,
            updated=first,
            events=(_event("first-proposal", proposal_key),),
        )
    )
    result = uow.reserve("sources", proposal_key)

    assert result.disposition is ReservationDisposition.ALREADY_COMMITTED
    assert result.snapshot.runtime_result == first.runtime_result
    assert [event.id for event in uow.events] == ["register", "first-proposal"]


def test_memory_uow_refuses_to_drop_a_prior_processed_command_key() -> None:
    uow = InMemoryCoreUnitOfWork()
    initial = _snapshot()
    initial = uow.commit(
        LifecycleCommit(
            source_set_id="sources",
            idempotency_key=_REGISTER_KEY,
            reservation_token=_reserve_token(uow, _REGISTER_KEY),
            updated=initial,
            events=(_event("register", _REGISTER_KEY),),
        )
    ).snapshot
    next_key = "sources:next:fixed"
    invalid = initial.model_copy(
        update={
            "workflow": initial.workflow.model_copy(
                update={"processed_idempotency_keys": frozenset({next_key})}
            )
        }
    )

    with pytest.raises(ValueError, match="command receipts and workflow keys differ"):
        uow.commit(
            LifecycleCommit(
                source_set_id="sources",
                idempotency_key=next_key,
                reservation_token=_reserve_token(uow, next_key),
                expected=initial,
                updated=invalid,
                events=(_event("next", next_key),),
            )
        )


def test_stale_reservation_token_cannot_commit_or_release_a_later_command() -> None:
    uow = InMemoryCoreUnitOfWork()
    initial = _snapshot()
    committed = uow.commit(
        LifecycleCommit(
            source_set_id="sources",
            idempotency_key=_REGISTER_KEY,
            reservation_token=_reserve_token(uow, _REGISTER_KEY),
            updated=initial,
            events=(_event("register", _REGISTER_KEY),),
        )
    )
    stale = uow.reserve("sources", "sources:stale:fixed")
    assert stale.disposition is ReservationDisposition.ACQUIRED
    assert stale.token is not None
    uow.release("sources", "sources:stale:fixed", stale.token)

    active = uow.reserve("sources", "sources:active:fixed")
    assert active.disposition is ReservationDisposition.ACQUIRED
    assert active.token is not None

    with pytest.raises(CommandInProgressError):
        uow.commit(
            LifecycleCommit(
                source_set_id="sources",
                idempotency_key="sources:stale:fixed",
                reservation_token=stale.token,
                expected=committed.snapshot,
                updated=committed.snapshot,
            )
        )

    uow.release("sources", "sources:stale:fixed", stale.token)
    blocked = uow.reserve("sources", "sources:third:fixed")
    assert blocked.disposition is ReservationDisposition.IN_PROGRESS
    uow.release("sources", "sources:active:fixed", active.token)
