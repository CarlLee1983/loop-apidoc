from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from loop_apidoc.adapters.fragments import acquire_fragment_bundle
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
from loop_apidoc.domain.projections import (
    OpenApiProjectionCompiler,
    ProvenanceProjectionCompiler,
    ReviewProjectionCompiler,
)
from loop_apidoc.domain.rules import ApiDomainRulePack
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.run.models import RunStatus
from loop_apidoc.shadow.bridge import (
    SHADOW_DOMAIN_VERSION,
    SHADOW_RUNTIME_IDENTITY,
    SHADOW_RUNTIME_VERSION,
    build_contract_metadata,
    build_fragment_requests,
    build_runtime_result,
    build_source_set,
    parse_bridge_diagnostic,
    with_materialized_evidence,
)
from loop_apidoc.shadow.models import (
    ShadowArtifacts,
    ShadowProjection,
    ShadowStage,
    compare_results,
)
from loop_apidoc.source_facts.models import FactIndex
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
    facts: FactIndex | None = None,
    sources_root: Path | None = None,
    legacy_report: ValidationReport,
    legacy_status: RunStatus,
    generated_at: datetime,
) -> ShadowArtifacts:
    try:
        bridge = build_source_set(manifest, generated_at)
    except Exception as exc:
        raise ShadowExecutionFailure(ShadowStage.BRIDGE, exc) from exc

    if facts is not None and sources_root is not None:
        try:
            materialized_manifest = manifest.model_copy(
                update={"sources_root": str(sources_root)}
            )
            evidence = acquire_fragment_bundle(
                bridge.source_set,
                materialized_manifest,
                facts,
                build_fragment_requests(plan, bridge),
                generated_at,
            )
            bridge = with_materialized_evidence(bridge, evidence)
        except Exception as exc:
            raise ShadowExecutionFailure(ShadowStage.ACQUISITION, exc) from exc

    try:
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
    except Exception as exc:
        raise ShadowExecutionFailure(ShadowStage.SERVICE, exc) from exc

    try:
        service.reconcile(source_set_id)
    except Exception as exc:
        raise ShadowExecutionFailure(ShadowStage.VERIFICATION, exc) from exc

    try:
        service.build_contract(source_set_id, metadata)
    except Exception as exc:
        raise ShadowExecutionFailure(ShadowStage.SERVICE, exc) from exc

    try:
        decision = service.validate(
            source_set_id,
            (
                OpenApiProjectionCompiler(version="2"),
                ReviewProjectionCompiler(version="2"),
                ProvenanceProjectionCompiler(version="1"),
            ),
        )
    except Exception as exc:
        raise ShadowExecutionFailure(ShadowStage.PROJECTION, exc) from exc

    try:
        claims = contract_store.get_claims(source_set_id)
        contract = contract_store.get_contract(source_set_id)
        workflow = contract_store.get_workflow(source_set_id)
    except Exception as exc:
        raise ShadowExecutionFailure(ShadowStage.SERVICE, exc) from exc

    relationships_by_id = {
        relationship.id: relationship
        for claim in claims
        for relationship in claim.support_relationships
    }
    relationships = tuple(
        relationships_by_id[key] for key in sorted(relationships_by_id)
    )
    projections = tuple(
        ShadowProjection(
            name=projection.name,
            version=projection.version,
            media_type=projection.media_type,
            payload=json.loads(projection.content),
        )
        for projection in contract_store.projections.get(source_set_id, ())
    )
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
        relationships=relationships,
        contract=contract,
        decision=decision,
        workflow=workflow,
        events=tuple(event_sink.events),
        comparison=comparison,
        projections=projections,
        artifact_publications=len(artifact_sink.publications),
        approval_requests=approval.requests,
    )
