from __future__ import annotations

from datetime import datetime

from loop_apidoc.adapters.memory import (
    FixedClock,
    InMemoryArtifactSink,
    InMemoryContractStore,
    InMemoryEventSink,
    InMemoryEvidenceStore,
    StaticSourceAdapter,
)
from loop_apidoc.adapters.runtime import CallableRuntimeAdapter
from loop_apidoc.core.models import ContractRelease, PolicyProfile
from loop_apidoc.core.service import EvidenceToContractService
from loop_apidoc.domain.rules import ApiDomainRulePack
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.run.models import RunStatus
from loop_apidoc.shadow.bridge import (
    SHADOW_DOMAIN_VERSION,
    SHADOW_RUNTIME_IDENTITY,
    SHADOW_RUNTIME_VERSION,
    build_contract_metadata,
    build_evidence,
    build_runtime_result,
    parse_bridge_diagnostic,
)
from loop_apidoc.shadow.models import (
    ShadowArtifacts,
    ShadowStage,
    compare_results,
)
from loop_apidoc.validate.models import ValidationReport


class ShadowExecutionFailure(RuntimeError):
    def __init__(self, stage: ShadowStage, cause: Exception) -> None:
        super().__init__(f"shadow {stage.value} failed")
        self.stage = stage
        self.cause = cause


class _NeverApprove:
    def __init__(self) -> None:
        self.requests = 0

    def request(self, release: ContractRelease):
        del release
        self.requests += 1
        raise RuntimeError("shadow execution must not request approval")


def execute_shadow(
    *,
    manifest: Manifest,
    plan: NormalizationPlan,
    legacy_report: ValidationReport,
    legacy_status: RunStatus,
    generated_at: datetime,
) -> ShadowArtifacts:
    try:
        bridge = build_evidence(manifest, generated_at)
        runtime_result = build_runtime_result(plan, bridge)
        metadata = build_contract_metadata(plan, bridge)
    except Exception as exc:
        raise ShadowExecutionFailure(ShadowStage.BRIDGE, exc) from exc

    evidence_store = InMemoryEvidenceStore()
    contract_store = InMemoryContractStore()
    artifact_sink = InMemoryArtifactSink()
    event_sink = InMemoryEventSink()
    approval = _NeverApprove()
    service = EvidenceToContractService(
        source=StaticSourceAdapter(bridge.evidence),
        runtime=CallableRuntimeAdapter(
            SHADOW_RUNTIME_IDENTITY,
            SHADOW_RUNTIME_VERSION,
            lambda _work_item: runtime_result,
        ),
        evidence_store=evidence_store,
        contract_store=contract_store,
        artifact_sink=artifact_sink,
        approval=approval,
        events=event_sink,
        clock=FixedClock(generated_at),
        domain_rules=ApiDomainRulePack(version=SHADOW_DOMAIN_VERSION),
        policy_profile=PolicyProfile(name="shadow"),
    )
    source_set_id = bridge.source_set.id
    try:
        service.register_source_set(bridge.source_set)
        service.acquire(source_set_id)
        service.request_claim_proposals(
            source_set_id,
            tuple(
                sorted(
                    {
                        proposal.claim_kind
                        for proposal in runtime_result.claim_proposals
                    }
                )
            ),
        )
        service.reconcile(source_set_id)
        service.build_contract(source_set_id, metadata)
        decision = service.validate(source_set_id)
        claims = contract_store.get_claims(source_set_id)
        contract = contract_store.get_contract(source_set_id)
        workflow = contract_store.get_workflow(source_set_id)
    except Exception as exc:
        raise ShadowExecutionFailure(ShadowStage.SERVICE, exc) from exc

    diagnostics = (
        *bridge.diagnostics,
        *(parse_bridge_diagnostic(message) for message in runtime_result.diagnostics),
    )
    try:
        comparison = compare_results(
            legacy_report=legacy_report,
            legacy_status=legacy_status,
            decision=decision,
            claims=claims,
            diagnostics=diagnostics,
        )
    except Exception as exc:
        raise ShadowExecutionFailure(ShadowStage.COMPARISON, exc) from exc

    return ShadowArtifacts(
        source_set=bridge.source_set,
        evidence=bridge.evidence,
        runtime_result=runtime_result,
        claims=claims,
        contract=contract,
        decision=decision,
        workflow=workflow,
        events=tuple(event_sink.events),
        comparison=comparison,
        artifact_publications=len(artifact_sink.publications),
        approval_requests=approval.requests,
    )
