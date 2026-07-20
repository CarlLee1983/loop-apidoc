from __future__ import annotations

import hashlib

from loop_apidoc.core.governance import (
    approve_release,
    make_candidate_release,
    publish_release,
    release_id_for_contract,
)
from loop_apidoc.core.lifecycle import LifecycleMachine
from loop_apidoc.core.models import (
    Actor,
    ActorKind,
    CurrentPointer,
    DomainEvent,
    ExtractionWorkItem,
    LifecycleState,
    PolicyProfile,
    ValidationVerdict,
    WorkflowRecord,
)
from loop_apidoc.core.policy import ValidationPolicyEngine
from loop_apidoc.core.ports import (
    ApprovalPort,
    ArtifactSink,
    Clock,
    ContractStore,
    EventSink,
    EvidenceStore,
    RuntimePort,
    SourcePort,
)
from loop_apidoc.core.reconciliation import reconcile_claims
from loop_apidoc.domain.builder import ContractClaimInput, build_grounded_contract
from loop_apidoc.domain.models import ContractMetadata
from loop_apidoc.domain.projections import ProjectionCompiler
from loop_apidoc.domain.rules import ApiDomainRulePack


class EvidenceToContractService:
    def __init__(
        self,
        *,
        source: SourcePort,
        runtime: RuntimePort,
        evidence_store: EvidenceStore,
        contract_store: ContractStore,
        artifact_sink: ArtifactSink,
        approval: ApprovalPort,
        events: EventSink,
        clock: Clock,
        domain_rules: ApiDomainRulePack,
        policy_profile: PolicyProfile | None = None,
    ) -> None:
        self.source = source
        self.runtime = runtime
        self.evidence_store = evidence_store
        self.contract_store = contract_store
        self.artifact_sink = artifact_sink
        self.approval_port = approval
        self.events = events
        self.clock = clock
        self.domain_rules = domain_rules
        self.policy_profile = policy_profile or PolicyProfile(name="strict")
        self.lifecycle = LifecycleMachine()
        self.policy = ValidationPolicyEngine()

    def register_source_set(self, source_set) -> WorkflowRecord:
        self.evidence_store.put_source_set(source_set)
        record = WorkflowRecord(
            source_set_id=source_set.id,
            state=LifecycleState.REGISTERED,
            artifacts=frozenset({"source_set"}),
        )
        self.contract_store.put_workflow(record)
        self.events.append(
            DomainEvent(
                id=_id(source_set.id, "register"),
                aggregate_id=source_set.id,
                kind="lifecycle.registered",
                actor=Actor(id="core", kind=ActorKind.SYSTEM),
                occurred_at=self.clock.now(),
            )
        )
        return record

    def acquire(self, source_set_id: str) -> None:
        source_set = self.evidence_store.get_source_set(source_set_id)
        bundle = self.source.acquire(source_set)
        self.evidence_store.put_bundle(bundle)
        self._transition(
            source_set_id,
            LifecycleState.ACQUIRED,
            Actor(id="source-adapter", kind=ActorKind.SYSTEM),
            "acquire",
            frozenset({"evidence_bundle"}),
        )

    def request_claim_proposals(
        self,
        source_set_id: str,
        requested_claim_kinds: tuple[str, ...],
    ) -> None:
        bundle = self.evidence_store.get_bundle(source_set_id)
        work_item = ExtractionWorkItem(
            task_id=_id(source_set_id, "proposal"),
            evidence_scope=tuple(fragment.id for fragment in bundle.fragments),
            requested_claim_kinds=requested_claim_kinds,
            output_schema="claim-proposal/v1",
            grounding_constraints=("evidence-reference-required",),
            correlation_id=_id(source_set_id, "correlation"),
        )
        result = self.runtime.propose(work_item)
        self.contract_store.put_runtime_result(source_set_id, result)
        record = self.contract_store.get_workflow(source_set_id)
        self.contract_store.put_workflow(
            record.model_copy(update={"runtime_identities": (result.runtime_identity,)})
        )
        self._transition(
            source_set_id,
            LifecycleState.CLAIMS_PROPOSED,
            Actor(id=result.runtime_identity, kind=ActorKind.RUNTIME),
            "propose",
            frozenset({"runtime_result"}),
        )

    def reconcile(self, source_set_id: str) -> None:
        result = self.contract_store.get_runtime_result(source_set_id)
        bundle = self.evidence_store.get_bundle(source_set_id)
        claims = reconcile_claims(
            result.claim_proposals,
            evidence_fragment_ids=frozenset(
                fragment.id for fragment in bundle.fragments
            ),
        )
        self.contract_store.put_claims(source_set_id, claims)
        self._transition(
            source_set_id,
            LifecycleState.RECONCILED,
            Actor(id="reconciler", kind=ActorKind.SYSTEM),
            "reconcile",
            frozenset({"grounded_claims"}),
        )

    def build_contract(self, source_set_id: str, metadata: ContractMetadata) -> None:
        claims = self.contract_store.get_claims(source_set_id)
        contract = build_grounded_contract(
            metadata,
            tuple(
                ContractClaimInput(
                    identity=claim.canonical_identity,
                    claim_kind=claim.claim_kind,
                    value=claim.value,
                    status=claim.status,
                    evidence_refs=claim.evidence_refs,
                )
                for claim in claims
            ),
        )
        self.contract_store.put_contract(source_set_id, contract)
        self._transition(
            source_set_id,
            LifecycleState.CONTRACT_BUILT,
            Actor(id="domain-pack", kind=ActorKind.SYSTEM),
            "build-contract",
            frozenset({"contract"}),
        )

    def validate(
        self,
        source_set_id: str,
        compilers: tuple[ProjectionCompiler, ...] = (),
    ):
        contract = self.contract_store.get_contract(source_set_id)
        decision = self.policy.decide(
            self.domain_rules.evaluate(contract),
            self.policy_profile,
            now=self.clock.now(),
        )
        if decision.verdict is ValidationVerdict.REJECT:
            self._transition(
                source_set_id,
                LifecycleState.VALIDATED,
                Actor(id="policy", kind=ActorKind.POLICY),
                "validate",
                frozenset({"validation_decision"}),
            )
            return decision
        projections = tuple(compiler.compile(contract) for compiler in compilers)
        self.contract_store.put_projections(source_set_id, projections)
        record = self.contract_store.get_workflow(source_set_id)
        candidate = make_candidate_release(
            contract,
            decision,
            runtime_identities=record.runtime_identities,
            core_version="1",
            policy_version=self.policy_profile.name,
            projection_versions=tuple(
                (compiler.name, compiler.version) for compiler in compilers
            ),
            now=self.clock.now(),
        )
        self.contract_store.put_release(candidate)
        self._transition(
            source_set_id,
            LifecycleState.VALIDATED,
            Actor(id="policy", kind=ActorKind.POLICY),
            "validate",
            frozenset({"validation_decision", "candidate_release", "projections"}),
        )
        target = (
            LifecycleState.REVIEW_REQUIRED
            if decision.verdict is ValidationVerdict.REVIEW
            else LifecycleState.APPROVAL_READY
        )
        self._transition(
            source_set_id,
            target,
            Actor(id="policy", kind=ActorKind.POLICY),
            "route-approval",
        )
        return decision

    def approve(self, source_set_id: str):
        contract = self.contract_store.get_contract(source_set_id)
        release_id = release_id_for_contract(contract)
        candidate = self.contract_store.get_release(release_id)
        approved = approve_release(candidate, self.approval_port.request(candidate))
        self.contract_store.put_release(approved)
        self._transition(
            source_set_id,
            LifecycleState.APPROVED,
            Actor(id=approved.approved_by or "approver", kind=ActorKind.APPROVER),
            "approve",
        )
        return approved

    def publish(self, source_set_id: str):
        contract = self.contract_store.get_contract(source_set_id)
        release_id = release_id_for_contract(contract)
        approved = self.contract_store.get_release(release_id)
        projections = self.contract_store.get_projections(source_set_id)
        refs = self.artifact_sink.publish(release_id, projections)
        published = publish_release(approved, refs, self.clock.now())
        self.contract_store.put_release(published)
        self.contract_store.put_current(
            CurrentPointer(
                contract_id=published.contract_id,
                release_id=published.release_id,
                status=published.status,
            )
        )
        self._transition(
            source_set_id,
            LifecycleState.PUBLISHED,
            Actor(id="publisher", kind=ActorKind.PUBLISHER),
            "publish",
        )
        return published

    def _transition(
        self, source_set_id, target, actor, key, artifacts=frozenset()
    ) -> None:
        record = self.contract_store.get_workflow(source_set_id)
        updated, event = self.lifecycle.transition(
            record,
            target,
            actor=actor,
            idempotency_key=f"{source_set_id}:{key}",
            artifacts=artifacts,
        )
        self.contract_store.put_workflow(updated)
        if event is not None:
            self.events.append(
                event.model_copy(update={"occurred_at": self.clock.now()})
            )


def _id(aggregate: str, action: str) -> str:
    return hashlib.sha256(f"{aggregate}:{action}".encode()).hexdigest()[:20]
