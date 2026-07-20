from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.adapters.memory import (
    FixedClock,
    InMemoryArtifactSink,
    InMemoryContractStore,
    InMemoryEventSink,
    InMemoryEvidenceStore,
    StaticApprovalAdapter,
    StaticSourceAdapter,
)
from loop_apidoc.adapters.runtime import CallableRuntimeAdapter
from loop_apidoc.core.models import (
    Actor,
    ActorKind,
    ApprovalDecision,
    ClaimProposal,
    EvidenceBundle,
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


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def test_source_to_published_release_is_a_governed_sequence():
    operation = {
        "method": "GET",
        "path": "/health",
        "responses": [{"status_code": "200", "description": "OK"}],
    }
    paths = material_claim_paths("operation", operation)
    source_set = SourceSet(
        id="sources",
        version="1",
        sources=(SourceDescriptor(id="manual", kind="memory", locator="manual"),),
    )
    bundle = EvidenceBundle(
        source_set_id="sources",
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
    runtime_result = RuntimeResult(
        claim_proposals=(
            ClaimProposal(
                id="proposal-1",
                claim_kind="operation",
                subject="GET /health",
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
                runtime_identity="parser",
            ),
        ),
        runtime_identity="parser",
        runtime_version="1",
    )
    evidence_store = InMemoryEvidenceStore()
    contract_store = InMemoryContractStore()
    artifacts = InMemoryArtifactSink()
    approval = ApprovalDecision(
        approved=True,
        actor=Actor(id="reviewer", kind=ActorKind.APPROVER),
        decided_at=NOW,
    )
    service = EvidenceToContractService(
        source=StaticSourceAdapter(bundle),
        runtime=CallableRuntimeAdapter("parser", "1", lambda _: runtime_result),
        evidence_store=evidence_store,
        contract_store=contract_store,
        artifact_sink=artifacts,
        approval=StaticApprovalAdapter(approval),
        events=InMemoryEventSink(),
        clock=FixedClock(NOW),
        domain_rules=ApiDomainRulePack(version="1"),
    )

    service.register_source_set(source_set)
    service.acquire(source_set.id)
    service.request_claim_proposals(source_set.id, ("operation",))
    service.reconcile(source_set.id)
    service.build_contract(
        source_set.id,
        ContractMetadata(
            contract_id="health",
            title="Health API",
            version="1",
            source_set_id="sources",
            source_set_version="1",
            domain_version="1",
        ),
    )
    service.validate(source_set.id, (OpenApiProjectionCompiler(version="1"),))
    service.approve(source_set.id)
    release = service.publish(source_set.id)

    assert release.status is ReleaseStatus.PUBLISHED
    assert release.projection_versions == (("openapi", "1"),)
    assert artifacts.publications[release.release_id][0].name == "openapi"
    assert release.artifact_refs == (f"memory://{release.release_id}/openapi",)
    assert all(
        binding.relationship_id is not None
        for binding in contract_store.get_contract("sources").operations[0].evidence
    )
