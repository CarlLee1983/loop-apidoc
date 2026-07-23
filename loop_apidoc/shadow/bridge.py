from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from loop_apidoc.adapters.fragments import FragmentRequest, parse_legacy_locator
from loop_apidoc.core.models import (
    ClaimSupportProposal,
    ClaimProposal,
    EvidenceBundle,
    EvidenceFragment,
    RuntimeResult,
    SourceArtifact,
    SourceDescriptor,
    SourceSet,
)
from loop_apidoc.domain.claim_paths import (
    claim_value_at,
    material_claim_paths,
)
from loop_apidoc.domain.evidence import (
    DerivationStep,
    FragmentPrecision,
    JsonPointerLocator,
    LineRangeLocator,
    PageLocator,
    SupportRelationshipType,
    TableCellLocator,
    VerificationMethod,
    WholeDocumentLocator,
    XPathLocator,
    CssSelectorLocator,
)
from loop_apidoc.domain.models import ContractMetadata, FrozenModel
from loop_apidoc.extraction.evidence import ExtractionEvidenceReference
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
)
from loop_apidoc.plan.claim_projection import iter_plan_claim_projections
from loop_apidoc.plan.models import NormalizationPlan, PlanItemStatus, SourceCitation
from loop_apidoc.shadow.models import BridgeDiagnostic


SHADOW_RUNTIME_IDENTITY = "loop-apidoc-legacy-plan-shadow"
SHADOW_RUNTIME_VERSION = "1"
SHADOW_DOMAIN_VERSION = "1"


class ShadowMetadataError(ValueError):
    """The source-derived plan cannot provide required contract metadata."""


class BridgeInputs(FrozenModel):
    source_set: SourceSet
    evidence: EvidenceBundle
    citation_fragments: tuple[tuple[str, tuple[str, ...]], ...]
    diagnostics: tuple[BridgeDiagnostic, ...] = ()
    source_set_digest: str

    def resolve_citation(self, manifest_source: str | None) -> tuple[str, ...]:
        if manifest_source is None:
            return ()
        return dict(self.citation_fragments).get(manifest_source, ())

    def fragments_for_citation(
        self,
        manifest_source: str | None,
    ) -> tuple[EvidenceFragment, ...]:
        ids = set(self.resolve_citation(manifest_source))
        return tuple(
            fragment for fragment in self.evidence.fragments if fragment.id in ids
        )


def build_evidence(manifest: Manifest, generated_at: datetime) -> BridgeInputs:
    metadata = _canonical_source_metadata(manifest)
    canonical = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    source_set_digest = hashlib.sha256(canonical.encode()).hexdigest()
    source_set_id = f"source-set-{source_set_digest[:20]}"

    descriptors: list[SourceDescriptor] = []
    artifacts: list[SourceArtifact] = []
    fragments: list[EvidenceFragment] = []
    citations: dict[str, set[str]] = {}
    local_fragments: dict[str, tuple[str, ...]] = {}
    diagnostics: list[BridgeDiagnostic] = []

    for source in sorted(manifest.local_sources, key=lambda item: item.relative_path):
        if not _usable_local_source(source):
            continue
        descriptor = _descriptor(
            kind="file",
            locator=source.relative_path,
            media_type=source.mime_type,
        )
        artifact, fragment = _artifact_and_fragment(
            descriptor=descriptor,
            digest=source.sha256,
            acquired_at=generated_at,
            media_type=source.mime_type or "application/octet-stream",
            acquisition_metadata=(("relative_path", source.relative_path),),
        )
        descriptors.append(descriptor)
        artifacts.append(artifact)
        fragments.append(fragment)
        citations.setdefault(source.relative_path, set()).add(fragment.id)
        local_fragments[source.relative_path] = (fragment.id,)

    urls_by_locator: dict[str, list] = {}
    for source in manifest.url_sources:
        urls_by_locator.setdefault(source.url, []).append(source)
    for url, sources in sorted(urls_by_locator.items()):
        descriptor = _descriptor(kind="url", locator=url, media_type=None)
        descriptors.append(descriptor)
        content_digests = {source.content_sha256 for source in sources}
        if len(content_digests) > 1:
            diagnostics.append(
                BridgeDiagnostic(
                    code="SOURCE_LOCATOR_AMBIGUOUS",
                    message=(
                        "duplicate URL locator has conflicting content digests "
                        "and cannot be used as evidence"
                    ),
                    manifest_source=url,
                )
            )
            continue
        content_digest = next(iter(content_digests))
        if content_digest is not None:
            artifact, fragment = _artifact_and_fragment(
                descriptor=descriptor,
                digest=content_digest,
                acquired_at=generated_at,
                media_type="application/octet-stream",
                acquisition_metadata=(("url", url),),
            )
            artifacts.append(artifact)
            fragments.append(fragment)
            citations.setdefault(url, set()).add(fragment.id)
        for snapshot_file in sorted(
            {
                source.snapshot_file
                for source in sources
                if source.snapshot_file is not None
            }
        ):
            if snapshot_file in local_fragments:
                citations.setdefault(url, set()).update(
                    local_fragments[snapshot_file]
                )

    source_set = SourceSet(
        id=source_set_id,
        version=source_set_digest,
        sources=tuple(descriptors),
    )
    evidence = EvidenceBundle(
        source_set_id=source_set.id,
        source_set_version=source_set.version,
        artifacts=tuple(artifacts),
        fragments=tuple(fragments),
    )
    return BridgeInputs(
        source_set=source_set,
        evidence=evidence,
        citation_fragments=tuple(
            (source, tuple(sorted(fragment_ids)))
            for source, fragment_ids in sorted(citations.items())
        ),
        diagnostics=tuple(diagnostics),
        source_set_digest=source_set_digest,
    )


def build_source_set(manifest: Manifest, generated_at: datetime) -> BridgeInputs:
    """Build deterministic logical source identity before adapter acquisition."""
    return build_evidence(manifest, generated_at)


def with_materialized_evidence(
    bridge: BridgeInputs,
    evidence: EvidenceBundle,
) -> BridgeInputs:
    descriptors = {source.id: source for source in bridge.source_set.sources}
    source_by_artifact = {
        artifact.id: artifact.source_id for artifact in evidence.artifacts
    }
    citations: dict[str, set[str]] = {}
    for fragment in evidence.fragments:
        source_id = source_by_artifact.get(fragment.source_artifact_id)
        descriptor = descriptors.get(source_id) if source_id is not None else None
        if descriptor is not None:
            citations.setdefault(descriptor.locator, set()).add(fragment.id)
    return bridge.model_copy(
        update={
            "evidence": evidence,
            "citation_fragments": tuple(
                (source, tuple(sorted(fragment_ids)))
                for source, fragment_ids in sorted(citations.items())
            ),
        }
    )


def build_fragment_requests(
    plan: NormalizationPlan,
    bridge: BridgeInputs,
) -> tuple[FragmentRequest, ...]:
    source_ids = {
        source.locator: source.id for source in bridge.source_set.sources
    }
    requests: dict[str, FragmentRequest] = {}
    for citation in _all_citations(plan):
        for reference in citation.evidence:
            source_id = source_ids.get(reference.source)
            if source_id is None:
                continue
            request = FragmentRequest(source_id=source_id, locator=reference.locator)
            key = _canonical_json(request.model_dump(mode="json"))
            requests[key] = request
        source_id = source_ids.get(citation.manifest_source or "")
        if source_id is None or citation.locator is None:
            continue
        locator = _citation_locator(citation)
        if locator.kind == "unresolved":
            continue
        request = FragmentRequest(source_id=source_id, locator=locator)
        key = _canonical_json(request.model_dump(mode="json"))
        requests[key] = request
    return tuple(requests[key] for key in sorted(requests))


def build_runtime_result(
    plan: NormalizationPlan,
    bridge: BridgeInputs,
) -> RuntimeResult:
    candidates = _proposal_candidates(plan, bridge)
    diagnostics: list[BridgeDiagnostic] = [
        diagnostic
        for candidate in candidates
        for diagnostic in candidate.diagnostics
    ]
    emitted: list[_ProposalCandidate] = []
    conflicting: dict[tuple[str, str, str], list[_ProposalCandidate]] = {}
    for candidate in candidates:
        if candidate.status is PlanItemStatus.CONFLICTING:
            conflicting.setdefault(candidate.identity, []).append(candidate)
        else:
            emitted.append(candidate)
    for identity, group in sorted(conflicting.items()):
        distinct = {
            _canonical_json(candidate.value): candidate for candidate in group
        }
        if len(distinct) < 2:
            location = group[0].plan_location
            diagnostics.append(
                BridgeDiagnostic(
                    code="CONFLICT_VALUES_UNAVAILABLE",
                    message=(
                        "legacy conflict does not preserve distinct values; "
                        "the preserved value remains unverified"
                    ),
                    plan_location=location,
                )
            )
            emitted.append(
                replace(
                    group[0],
                    evidence_refs=(),
                    support_proposals=(),
                    diagnostics=(),
                )
            )
            continue
        emitted.extend(distinct[key] for key in sorted(distinct))

    proposals = tuple(
        _to_claim_proposal(candidate)
        for candidate in emitted
    )
    return RuntimeResult(
        claim_proposals=proposals,
        diagnostics=tuple(_diagnostic_text(item) for item in diagnostics),
        runtime_identity=SHADOW_RUNTIME_IDENTITY,
        runtime_version=SHADOW_RUNTIME_VERSION,
    )


def build_contract_metadata(
    plan: NormalizationPlan,
    bridge: BridgeInputs,
) -> ContractMetadata:
    title = plan.resolved_title
    version = plan.resolved_version
    if not title or not title.strip():
        raise ShadowMetadataError(
            "shadow contract metadata requires a source-stated title"
        )
    return ContractMetadata(
        contract_id=f"contract-{bridge.source_set_digest[:20]}",
        title=title,
        version=version.strip() if version and version.strip() else None,
        source_set_id=bridge.source_set.id,
        source_set_version=bridge.source_set.version,
        domain_version=SHADOW_DOMAIN_VERSION,
    )


@dataclass(frozen=True)
class _ProposalCandidate:
    plan_location: str
    status: PlanItemStatus
    claim_kind: str
    subject: str
    predicate: str
    value: Any
    evidence_refs: tuple[str, ...]
    support_proposals: tuple[ClaimSupportProposal, ...]
    diagnostics: tuple[BridgeDiagnostic, ...]

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.claim_kind, self.subject, self.predicate


def _proposal_candidates(
    plan: NormalizationPlan,
    bridge: BridgeInputs,
) -> list[_ProposalCandidate]:
    candidates: list[_ProposalCandidate] = []
    for projection in iter_plan_claim_projections(plan):
        candidates.append(
            _candidate(
                entry=projection.entry,
                plan_location=projection.plan_location,
                claim_kind=projection.claim_kind,
                subject=projection.subject,
                value=projection.value,
                bridge=bridge,
            )
        )
    return candidates


def _candidate(
    *,
    entry,
    plan_location: str,
    claim_kind: str,
    subject: str,
    value: dict[str, Any],
    bridge: BridgeInputs,
) -> _ProposalCandidate:
    evidence_refs, diagnostics = _resolve_citations(
        entry.citations,
        plan_location,
        bridge,
        require_citation=entry.status
        in {PlanItemStatus.SUPPORTED, PlanItemStatus.CONFLICTING},
    )
    status = entry.status
    support_proposals: tuple[ClaimSupportProposal, ...] = ()
    support_diagnostics: tuple[BridgeDiagnostic, ...] = ()
    if status in {PlanItemStatus.SUPPORTED, PlanItemStatus.CONFLICTING}:
        support_proposals, support_diagnostics = _semantic_support_proposals(
            citations=entry.citations,
            plan_location=plan_location,
            claim_kind=claim_kind,
            value=value,
            bridge=bridge,
        )
    if status is PlanItemStatus.MISSING:
        value = None
    elif status is PlanItemStatus.UNVERIFIED:
        evidence_refs = ()
        support_proposals = ()
    return _ProposalCandidate(
        plan_location=plan_location,
        status=status,
        claim_kind=claim_kind,
        subject=subject,
        predicate="definition",
        value=value,
        evidence_refs=evidence_refs,
        support_proposals=support_proposals,
        diagnostics=(*diagnostics, *support_diagnostics),
    )


def _resolve_citations(
    citations: list[SourceCitation],
    plan_location: str,
    bridge: BridgeInputs,
    *,
    require_citation: bool,
) -> tuple[tuple[str, ...], tuple[BridgeDiagnostic, ...]]:
    refs: set[str] = set()
    diagnostics: list[BridgeDiagnostic] = []
    if require_citation and not citations:
        diagnostics.append(
            BridgeDiagnostic(
                code="CITATION_MISSING",
                message="source-grounded plan entry has no citation",
                plan_location=plan_location,
            )
        )
    for citation in citations:
        source = citation.manifest_source
        if source is None:
            diagnostics.append(
                BridgeDiagnostic(
                    code="CITATION_SOURCE_MISSING",
                    message="citation has no manifest_source",
                    plan_location=plan_location,
                    query_id=citation.query_id,
                    answer_path=citation.answer_path,
                )
            )
            continue
        resolved = bridge.resolve_citation(source)
        if not resolved:
            diagnostics.append(
                BridgeDiagnostic(
                    code="CITATION_UNRESOLVED",
                    message="citation does not resolve to an acquired usable source",
                    plan_location=plan_location,
                    manifest_source=source,
                    query_id=citation.query_id,
                    answer_path=citation.answer_path,
                )
            )
            continue
        refs.update(resolved)
    return tuple(sorted(refs)), tuple(diagnostics)


def _to_claim_proposal(candidate: _ProposalCandidate) -> ClaimProposal:
    stable_input = {
        "plan_location": candidate.plan_location,
        "claim_kind": candidate.claim_kind,
        "subject": candidate.subject,
        "predicate": candidate.predicate,
        "value": candidate.value,
        "support_proposals": [
            proposal.model_dump(mode="json")
            for proposal in candidate.support_proposals
        ],
    }
    digest = hashlib.sha256(_canonical_json(stable_input).encode()).hexdigest()[:20]
    return ClaimProposal(
        id=f"proposal-{digest}",
        claim_kind=candidate.claim_kind,
        subject=candidate.subject,
        predicate=candidate.predicate,
        value=candidate.value,
        evidence_refs=candidate.evidence_refs,
        support_proposals=candidate.support_proposals,
        runtime_identity=SHADOW_RUNTIME_IDENTITY,
        runtime_observation=candidate.plan_location,
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _diagnostic_text(diagnostic: BridgeDiagnostic) -> str:
    return _canonical_json(diagnostic.model_dump(mode="json"))


def parse_bridge_diagnostic(value: str) -> BridgeDiagnostic:
    return BridgeDiagnostic.model_validate_json(value)


def _semantic_support_proposals(
    *,
    citations: list[SourceCitation],
    plan_location: str,
    claim_kind: str,
    value: Any,
    bridge: BridgeInputs,
) -> tuple[
    tuple[ClaimSupportProposal, ...],
    tuple[BridgeDiagnostic, ...],
]:
    proposals: dict[str, ClaimSupportProposal] = {}
    diagnostics: list[BridgeDiagnostic] = []
    paths = material_claim_paths(claim_kind, value)
    for path in paths:
        exact: list[
            tuple[
                EvidenceFragment,
                VerificationMethod,
                ExtractionEvidenceReference | None,
            ]
        ] = []
        degraded: list[EvidenceFragment] = []
        direct = _direct_evidence_for_path(citations, path)
        if direct:
            for citation, reference in direct:
                selected = [
                    fragment
                    for fragment in bridge.fragments_for_citation(reference.source)
                    if fragment.locator == reference.locator
                    and fragment.fragment_digest == reference.fragment_digest
                    and fragment.precision is FragmentPrecision.EXACT
                ]
                if selected:
                    exact.extend(
                        (fragment, _verification_method(fragment), reference)
                        for fragment in selected
                    )
                    continue
                diagnostics.append(
                    BridgeDiagnostic(
                        code="EXACT_EVIDENCE_UNRESOLVED",
                        message=(
                            "v1 exact evidence reference was not materialized "
                            "with its asserted digest"
                        ),
                        plan_location=plan_location,
                        manifest_source=reference.source,
                        query_id=citation.query_id,
                        answer_path=citation.answer_path,
                    )
                )
        else:
            for citation in citations:
                fragments = bridge.fragments_for_citation(citation.manifest_source)
                document = [
                    fragment
                    for fragment in fragments
                    if isinstance(fragment.locator, WholeDocumentLocator)
                ]
                if citation.locator is not None:
                    locator = _citation_locator(citation)
                    if locator.kind == "unresolved":
                        diagnostics.append(
                            BridgeDiagnostic(
                                code="LOCATOR_UNRESOLVED",
                                message="legacy citation locator is ambiguous",
                                plan_location=plan_location,
                                manifest_source=citation.manifest_source,
                                query_id=citation.query_id,
                                answer_path=citation.answer_path,
                            )
                        )
                        degraded.extend(document)
                        continue
                    selected = [
                        fragment
                        for fragment in fragments
                        if fragment.locator == locator
                        and fragment.precision is FragmentPrecision.EXACT
                        and _fragment_is_applicable(
                            fragment,
                            claim_kind,
                            value,
                            path,
                        )
                    ]
                    exact.extend(
                        (fragment, _verification_method(fragment), None)
                        for fragment in selected
                    )
                    if not selected:
                        degraded.extend(document)
                    continue
                selected = _source_fact_fragments_for_path(fragments, path)
                exact.extend(
                    (fragment, _verification_method(fragment), None)
                    for fragment in selected
                )
                if not selected:
                    degraded.extend(document)

        if exact:
            schema_ref_proposal = _ref_linked_schema_two_hop_support_proposal(
                exact=exact,
                claim_kind=claim_kind,
                value=value,
                claim_path=path,
                plan_location=plan_location,
            )
            if schema_ref_proposal is None:
                schema_ref_proposal = _ref_linked_schema_property_required_support_proposal(
                exact=exact,
                claim_kind=claim_kind,
                value=value,
                claim_path=path,
                plan_location=plan_location,
                )
            if schema_ref_proposal is None:
                schema_ref_proposal = _ref_linked_schema_property_support_proposal(
                    exact=exact,
                    claim_kind=claim_kind,
                    value=value,
                    claim_path=path,
                    plan_location=plan_location,
                )
            if schema_ref_proposal is not None:
                proposals[
                    _canonical_json(schema_ref_proposal.model_dump(mode="json"))
                ] = schema_ref_proposal
                continue
            ref_linked_proposal = _ref_linked_body_property_support_proposal(
                exact=exact,
                claim_kind=claim_kind,
                value=value,
                claim_path=path,
                plan_location=plan_location,
            )
            if ref_linked_proposal is None:
                ref_linked_proposal = _ref_linked_body_required_support_proposal(
                    exact=exact,
                    claim_kind=claim_kind,
                    value=value,
                    claim_path=path,
                    plan_location=plan_location,
                )
            if ref_linked_proposal is not None:
                proposals[
                    _canonical_json(ref_linked_proposal.model_dump(mode="json"))
                ] = ref_linked_proposal
                continue
            for fragment, method, reference in exact:
                proposal = _claim_support_proposal(
                    fragment=fragment,
                    method=method,
                    claim_kind=claim_kind,
                    value=value,
                    claim_path=path,
                    plan_location=plan_location,
                    exact_reference=reference,
                )
                proposals[_canonical_json(proposal.model_dump(mode="json"))] = proposal
            continue

        if degraded:
            fragment = sorted(degraded, key=lambda item: item.id)[0]
            proposal = ClaimSupportProposal(
                fragment_id=fragment.id,
                claim_path=path,
                proposed_relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
                verification_method=VerificationMethod.EXACT_NORMALIZED_VALUE,
                runtime_observation=plan_location,
            )
            proposals[_canonical_json(proposal.model_dump(mode="json"))] = proposal
        diagnostics.append(
            BridgeDiagnostic(
                code="CLAIM_PATH_UNSUPPORTED",
                message=f"no exact deterministic fragment supports claim path {path}",
                plan_location=plan_location,
            )
        )

    if paths and not all(
        any(proposal.claim_path == path for proposal in proposals.values())
        and any(
            proposal.claim_path == path
            and bridge.evidence.fragments[
                _fragment_index(bridge.evidence, proposal.fragment_id)
            ].precision
            is FragmentPrecision.EXACT
            for proposal in proposals.values()
        )
        for path in paths
    ):
        diagnostics.append(
            BridgeDiagnostic(
                code="LEGACY_CITATION_DEGRADED",
                message=(
                    "legacy citation could not be mapped to exact fragments "
                    "for every material claim path"
                ),
                plan_location=plan_location,
            )
        )
    return (
        tuple(proposals[key] for key in sorted(proposals)),
        tuple(_unique_diagnostics(diagnostics)),
    )


def _claim_support_proposal(
    *,
    fragment: EvidenceFragment,
    method: VerificationMethod,
    claim_kind: str,
    value: Any,
    claim_path: str,
    plan_location: str,
    exact_reference: ExtractionEvidenceReference | None,
) -> ClaimSupportProposal:
    derivation_name = (
        _openapi_pointer_derivation_name(claim_kind, claim_path, fragment)
        if exact_reference is not None
        else None
    )
    if derivation_name is None:
        if (
            exact_reference is not None
            and method is VerificationMethod.EXACT_NORMALIZED_VALUE
        ):
            method = VerificationMethod.CLAIM_BOUND_EXACT_REFERENCE
        return ClaimSupportProposal(
            fragment_id=fragment.id,
            claim_path=claim_path,
            proposed_relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
            verification_method=method,
            runtime_observation=plan_location,
        )
    claim_value = claim_value_at(claim_kind, value, claim_path)
    derivation_input = {
        "locator": fragment.locator.model_dump(mode="json"),
        "semantic_value": fragment.semantic_value,
    }
    return ClaimSupportProposal(
        fragment_id=fragment.id,
        claim_path=claim_path,
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name=derivation_name,
                version="1",
                input_digests=(_digest_value(derivation_input),),
                output_digest=_digest_value(claim_value),
            ),
        ),
        runtime_observation=plan_location,
    )


def _ref_linked_schema_property_required_support_proposal(
    *,
    exact: list[
        tuple[
            EvidenceFragment,
            VerificationMethod,
            ExtractionEvidenceReference | None,
        ]
    ],
    claim_kind: str,
    value: Any,
    claim_path: str,
    plan_location: str,
) -> ClaimSupportProposal | None:
    """Group a one-hop component-ref schema required claim from two v1 refs."""
    claim_parts = claim_path.strip("/").split("/")
    if (
        claim_kind != "schema"
        or not isinstance(value, Mapping)
        or not isinstance(value.get("name"), str)
        or len(claim_parts) != 3
        or claim_parts[0] != "fields"
        or claim_parts[2] != "required"
    ):
        return None
    claim_value = claim_value_at(claim_kind, value, claim_path)
    if not isinstance(claim_value, bool):
        return None
    field_name = claim_parts[1]
    if field_name.count(".") != 1:
        return None
    prefix, child_name = field_name.split(".", 1)
    v1_fragments = tuple(
        (fragment, reference)
        for fragment, _method, reference in exact
        if reference is not None and isinstance(fragment.locator, JsonPointerLocator)
    )
    for schema_fragment, _schema_reference in sorted(
        v1_fragments,
        key=lambda item: item[0].id,
    ):
        schema_parts = _json_pointer_parts(schema_fragment.locator.pointer)
        if (
            schema_parts is None
            or len(schema_parts) != 3
            or schema_parts[:2] != ("components", "schemas")
            or not isinstance(schema_fragment.semantic_value, Mapping)
        ):
            continue
        properties = schema_fragment.semantic_value.get("properties")
        property_name = child_name.removesuffix("[]")
        source_property = (
            properties.get(property_name) if isinstance(properties, Mapping) else None
        )
        if not isinstance(source_property, Mapping):
            continue
        if child_name.endswith("[]") != (source_property.get("type") == "array"):
            continue
        for context_fragment, _context_reference in sorted(
            v1_fragments,
            key=lambda item: item[0].id,
        ):
            if context_fragment.id == schema_fragment.id:
                continue
            context_parts = _json_pointer_parts(context_fragment.locator.pointer)
            is_array_item = (
                context_parts is not None
                and len(context_parts) == 7
                and context_parts[:2] == ("components", "schemas")
                and context_parts[3] == "properties"
                and context_parts[5:] == ("items", "$ref")
            )
            is_direct_property = (
                context_parts is not None
                and len(context_parts) == 6
                and context_parts[:2] == ("components", "schemas")
                and context_parts[3] == "properties"
                and context_parts[5] == "$ref"
            )
            expected_prefix = (
                f"{context_parts[4]}[]" if is_array_item else context_parts[4]
            ) if context_parts is not None else None
            if (
                not (is_array_item or is_direct_property)
                or context_parts is None
                or context_parts[2] != value["name"]
                or expected_prefix != prefix
                or _local_openapi_schema_name(context_fragment.semantic_value)
                != schema_parts[2]
            ):
                continue
            derivation_inputs = tuple(
                {
                    "locator": candidate.locator.model_dump(mode="json"),
                    "semantic_value": candidate.semantic_value,
                }
                for candidate in (schema_fragment, context_fragment)
            )
            return ClaimSupportProposal(
                fragment_id=schema_fragment.id,
                context_fragment_ids=(context_fragment.id,),
                claim_path=claim_path,
                proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
                verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
                derivation_steps=(
                    DerivationStep(
                        name=(
                            "openapi_schema_ref_property_required_from_fragments"
                        ),
                        version="1",
                        input_digests=tuple(
                            _digest_value(item) for item in derivation_inputs
                        ),
                        output_digest=_digest_value(claim_value),
                    ),
                ),
                runtime_observation=plan_location,
            )
    return None


def _ref_linked_schema_two_hop_support_proposal(
    *,
    exact: list[tuple[EvidenceFragment, VerificationMethod, ExtractionEvidenceReference | None]],
    claim_kind: str,
    value: Any,
    claim_path: str,
    plan_location: str,
) -> ClaimSupportProposal | None:
    """Group exactly two ordered array-item refs for one schema field claim."""
    parts = claim_path.strip("/").split("/")
    if (
        claim_kind != "schema" or not isinstance(value, Mapping)
        or not isinstance(value.get("name"), str) or len(parts) != 3
        or parts[0] != "fields" or parts[2] not in {"name", "type", "required"}
        or parts[1].count(".") != 2
    ):
        return None
    first_name, second_name, leaf_name = parts[1].split(".", 2)
    if not first_name.endswith("[]") or not second_name.endswith("[]"):
        return None
    claim_value = claim_value_at(claim_kind, value, claim_path)
    v1 = [(f, r) for f, _m, r in exact if r is not None and isinstance(f.locator, JsonPointerLocator)]
    contexts = []
    for fragment, _ref in v1:
        pointer = _json_pointer_parts(fragment.locator.pointer)
        if pointer and len(pointer) == 7 and pointer[:2] == ("components", "schemas") and pointer[3] == "properties" and pointer[5:] == ("items", "$ref"):
            contexts.append((fragment, pointer))
    for first_fragment, first_pointer in contexts:
        if first_pointer[2] != value["name"] or first_pointer[4] != first_name.removesuffix("[]"):
            continue
        entry_schema = _local_openapi_schema_name(first_fragment.semantic_value)
        if entry_schema is None:
            continue
        for second_fragment, second_pointer in contexts:
            if second_fragment.id == first_fragment.id or second_pointer[2] != entry_schema or second_pointer[4] != second_name.removesuffix("[]"):
                continue
            leaf_schema = _local_openapi_schema_name(second_fragment.semantic_value)
            if leaf_schema is None:
                continue
            for primary, _primary_ref in v1:
                primary_pointer = _json_pointer_parts(primary.locator.pointer)
                is_property = primary_pointer is not None and len(primary_pointer) == 5 and primary_pointer[:2] == ("components", "schemas") and primary_pointer[3] == "properties"
                is_schema = primary_pointer is not None and len(primary_pointer) == 3 and primary_pointer[:2] == ("components", "schemas")
                if primary_pointer is None or primary_pointer[2] != leaf_schema or (parts[2] == "required" and not is_schema) or (parts[2] != "required" and not is_property):
                    continue
                if parts[2] == "required":
                    properties = primary.semantic_value.get("properties") if isinstance(primary.semantic_value, Mapping) else None
                    source_property = properties.get(leaf_name.removesuffix("[]")) if isinstance(properties, Mapping) else None
                    expected = leaf_name.removesuffix("[]") in primary.semantic_value.get("required", ()) if isinstance(primary.semantic_value, Mapping) else None
                else:
                    source_property = primary.semantic_value
                    expected = (f"{first_name}.{second_name}.{leaf_name}" if parts[2] == "name" else source_property.get("type")) if isinstance(source_property, Mapping) else None
                if not isinstance(source_property, Mapping) or leaf_name.endswith("[]") != (source_property.get("type") == "array") or expected != claim_value:
                    continue
                inputs = tuple({"locator": item.locator.model_dump(mode="json"), "semantic_value": item.semantic_value} for item in (primary, first_fragment, second_fragment))
                return ClaimSupportProposal(
                    fragment_id=primary.id, context_fragment_ids=(first_fragment.id, second_fragment.id), claim_path=claim_path,
                    proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT, verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
                    derivation_steps=(DerivationStep(
                        name=f"openapi_schema_two_hop_ref_property_{parts[2]}_from_fragments", version="1",
                        input_digests=tuple(_digest_value(item) for item in inputs), output_digest=_digest_value(claim_value),
                    ),), runtime_observation=plan_location,
                )
    return None


def _ref_linked_schema_property_support_proposal(
    *,
    exact: list[
        tuple[
            EvidenceFragment,
            VerificationMethod,
            ExtractionEvidenceReference | None,
        ]
    ],
    claim_kind: str,
    value: Any,
    claim_path: str,
    plan_location: str,
) -> ClaimSupportProposal | None:
    """Group a one-hop component-ref field claim from two v1 fragments.

    The primary property belongs to the referenced component.  The context
    fragment exposes the root schema's direct property or array-item ``$ref``.
    Core repeats these structural checks before accepting the derivation.
    """
    claim_parts = claim_path.strip("/").split("/")
    if (
        claim_kind != "schema"
        or not isinstance(value, Mapping)
        or len(claim_parts) != 3
        or claim_parts[0] != "fields"
        or claim_parts[2] not in {"name", "type"}
        or not isinstance(value.get("name"), str)
    ):
        return None
    claim_value = claim_value_at(claim_kind, value, claim_path)
    v1_fragments = tuple(
        (fragment, reference)
        for fragment, _method, reference in exact
        if reference is not None and isinstance(fragment.locator, JsonPointerLocator)
    )
    for property_fragment, _property_reference in sorted(
        v1_fragments,
        key=lambda item: item[0].id,
    ):
        property_parts = _json_pointer_parts(property_fragment.locator.pointer)
        if (
            property_parts is None
            or len(property_parts) != 5
            or property_parts[:2] != ("components", "schemas")
            or property_parts[3] != "properties"
            or not isinstance(property_fragment.semantic_value, Mapping)
        ):
            continue
        item_schema = property_parts[2]
        item_property = property_parts[4]
        source_type = property_fragment.semantic_value.get("type")
        if source_type is not None and not isinstance(source_type, str):
            continue
        for context_fragment, _context_reference in sorted(
            v1_fragments,
            key=lambda item: item[0].id,
        ):
            if context_fragment.id == property_fragment.id:
                continue
            context_parts = _json_pointer_parts(context_fragment.locator.pointer)
            is_array_item = (
                context_parts is not None
                and len(context_parts) == 7
                and context_parts[:2] == ("components", "schemas")
                and context_parts[3] == "properties"
                and context_parts[5:] == ("items", "$ref")
            )
            is_direct_property = (
                context_parts is not None
                and len(context_parts) == 6
                and context_parts[:2] == ("components", "schemas")
                and context_parts[3] == "properties"
                and context_parts[5] == "$ref"
            )
            if (
                not (is_array_item or is_direct_property)
                or context_parts is None
                or context_parts[2] != value["name"]
                or _local_openapi_schema_name(context_fragment.semantic_value)
                != item_schema
            ):
                continue
            prefix = f"{context_parts[4]}[]" if is_array_item else context_parts[4]
            suffix = "[]" if source_type == "array" else ""
            field_name = f"{prefix}.{item_property}{suffix}"
            expected_value = field_name if claim_parts[2] == "name" else source_type
            if expected_value is None or expected_value != claim_value:
                continue
            derivation_inputs = tuple(
                {
                    "locator": candidate.locator.model_dump(mode="json"),
                    "semantic_value": candidate.semantic_value,
                }
                for candidate in (property_fragment, context_fragment)
            )
            return ClaimSupportProposal(
                fragment_id=property_fragment.id,
                context_fragment_ids=(context_fragment.id,),
                claim_path=claim_path,
                proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
                verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
                derivation_steps=(
                    DerivationStep(
                        name=(
                            "openapi_schema_ref_property_name_from_fragments"
                            if claim_parts[2] == "name"
                            else "openapi_schema_ref_property_type_from_fragments"
                        ),
                        version="1",
                        input_digests=tuple(
                            _digest_value(item) for item in derivation_inputs
                        ),
                        output_digest=_digest_value(claim_value),
                    ),
                ),
                runtime_observation=plan_location,
            )
    return None


def _ref_linked_body_property_support_proposal(
    *,
    exact: list[
        tuple[
            EvidenceFragment,
            VerificationMethod,
            ExtractionEvidenceReference | None,
        ]
    ],
    claim_kind: str,
    value: Any,
    claim_path: str,
    plan_location: str,
) -> ClaimSupportProposal | None:
    """Create the one-hop array-item mapping only from two v1 fragments.

    The Core repeats every structural check.  This adapter-side selection only
    groups the two exact references that jointly own one claimed body field.
    """
    parts = claim_path.strip("/").split("/")
    if (
        len(parts) != 4
        or parts[0] != "parameters"
        or parts[1] != "body"
        or parts[3] != "name"
        or not isinstance(value, Mapping)
    ):
        return None
    claim_value = claim_value_at(claim_kind, value, claim_path)
    if not isinstance(claim_value, str):
        return None
    v1_fragments = tuple(
        (fragment, reference)
        for fragment, _method, reference in exact
        if reference is not None and isinstance(fragment.locator, JsonPointerLocator)
    )
    for property_fragment, _property_reference in sorted(
        v1_fragments,
        key=lambda item: item[0].id,
    ):
        property_parts = _json_pointer_parts(property_fragment.locator.pointer)
        if (
            property_parts is None
            or len(property_parts) != 5
            or property_parts[:2] != ("components", "schemas")
            or property_parts[3] != "properties"
        ):
            continue
        item_schema = property_parts[2]
        item_property = property_parts[4]
        for context_fragment, _context_reference in sorted(
            v1_fragments,
            key=lambda item: item[0].id,
        ):
            if context_fragment.id == property_fragment.id:
                continue
            context_parts = _json_pointer_parts(context_fragment.locator.pointer)
            if (
                context_parts is None
                or len(context_parts) != 7
                or context_parts[:2] != ("components", "schemas")
                or context_parts[3] != "properties"
                or context_parts[5:] != ("items", "$ref")
                or value.get("request_schema_ref") != context_parts[2]
                or _local_openapi_schema_name(context_fragment.semantic_value)
                != item_schema
            ):
                continue
            suffix = "[]" if (
                isinstance(property_fragment.semantic_value, Mapping)
                and property_fragment.semantic_value.get("type") == "array"
            ) else ""
            derived_value = f"{context_parts[4]}[].{item_property}{suffix}"
            if derived_value != claim_value:
                continue
            derivation_inputs = tuple(
                {
                    "locator": candidate.locator.model_dump(mode="json"),
                    "semantic_value": candidate.semantic_value,
                }
                for candidate in (property_fragment, context_fragment)
            )
            return ClaimSupportProposal(
                fragment_id=property_fragment.id,
                context_fragment_ids=(context_fragment.id,),
                claim_path=claim_path,
                proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
                verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
                derivation_steps=(
                    DerivationStep(
                        name=(
                            "openapi_request_body_ref_property_name_from_fragments"
                        ),
                        version="1",
                        input_digests=tuple(
                            _digest_value(item) for item in derivation_inputs
                        ),
                        output_digest=_digest_value(claim_value),
                    ),
                ),
                runtime_observation=plan_location,
            )
    return None


def _ref_linked_body_required_support_proposal(
    *,
    exact: list[
        tuple[
            EvidenceFragment,
            VerificationMethod,
            ExtractionEvidenceReference | None,
        ]
    ],
    claim_kind: str,
    value: Any,
    claim_path: str,
    plan_location: str,
) -> ClaimSupportProposal | None:
    """Create a one-hop array-item required mapping from two v1 fragments."""
    parts = claim_path.strip("/").split("/")
    if (
        len(parts) != 4
        or parts[:2] != ["parameters", "body"]
        or parts[3] != "required"
        or not isinstance(value, Mapping)
    ):
        return None
    claim_value = claim_value_at(claim_kind, value, claim_path)
    if not isinstance(claim_value, bool):
        return None
    field_name = parts[2]
    if field_name.count(".") != 1:
        return None
    outer_name, _child_name = field_name.split(".", 1)
    if not outer_name.endswith("[]"):
        return None
    v1_fragments = tuple(
        (fragment, reference)
        for fragment, _method, reference in exact
        if reference is not None and isinstance(fragment.locator, JsonPointerLocator)
    )
    for schema_fragment, _schema_reference in sorted(
        v1_fragments,
        key=lambda item: item[0].id,
    ):
        schema_parts = _json_pointer_parts(schema_fragment.locator.pointer)
        if (
            schema_parts is None
            or len(schema_parts) != 3
            or schema_parts[:2] != ("components", "schemas")
            or not isinstance(schema_fragment.semantic_value, Mapping)
        ):
            continue
        for context_fragment, _context_reference in sorted(
            v1_fragments,
            key=lambda item: item[0].id,
        ):
            if context_fragment.id == schema_fragment.id:
                continue
            context_parts = _json_pointer_parts(context_fragment.locator.pointer)
            if (
                context_parts is None
                or len(context_parts) != 7
                or context_parts[:2] != ("components", "schemas")
                or context_parts[3] != "properties"
                or context_parts[5:] != ("items", "$ref")
                or value.get("request_schema_ref") != context_parts[2]
                or context_parts[4] != outer_name.removesuffix("[]")
                or _local_openapi_schema_name(context_fragment.semantic_value)
                != schema_parts[2]
            ):
                continue
            derivation_inputs = tuple(
                {
                    "locator": candidate.locator.model_dump(mode="json"),
                    "semantic_value": candidate.semantic_value,
                }
                for candidate in (schema_fragment, context_fragment)
            )
            return ClaimSupportProposal(
                fragment_id=schema_fragment.id,
                context_fragment_ids=(context_fragment.id,),
                claim_path=claim_path,
                proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
                verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
                derivation_steps=(
                    DerivationStep(
                        name=(
                            "openapi_request_body_ref_property_required_from_fragments"
                        ),
                        version="1",
                        input_digests=tuple(
                            _digest_value(item) for item in derivation_inputs
                        ),
                        output_digest=_digest_value(claim_value),
                    ),
                ),
                runtime_observation=plan_location,
            )
    return None


def _openapi_pointer_derivation_name(
    claim_kind: str,
    claim_path: str,
    fragment: EvidenceFragment,
) -> str | None:
    if not isinstance(fragment.locator, JsonPointerLocator):
        return None
    pointer_parts = _json_pointer_parts(fragment.locator.pointer)
    if claim_kind == "schema":
        if (
            claim_path == "/name"
            and pointer_parts is not None
            and len(pointer_parts) == 3
            and pointer_parts[:2] == ("components", "schemas")
        ):
            return "openapi_schema_name_from_pointer"
        claim_parts = claim_path.strip("/").split("/")
        if (
            len(claim_parts) == 3
            and claim_parts[0] == "fields"
            and claim_parts[2] in {"name", "type"}
            and pointer_parts is not None
            and len(pointer_parts) >= 5
            and pointer_parts[:2] == ("components", "schemas")
            and pointer_parts[3] == "properties"
        ):
            return {
                "name": "openapi_schema_property_name_from_pointer",
                "type": "openapi_schema_property_type_from_pointer",
            }[claim_parts[2]]
        if (
            len(claim_parts) == 3
            and claim_parts[0] == "fields"
            and claim_parts[2] == "required"
            and pointer_parts is not None
            and len(pointer_parts) == 3
            and pointer_parts[:2] == ("components", "schemas")
        ):
            return "openapi_schema_property_required_from_schema_pointer"
        return None
    direct = {
        "/method": "openapi_method_from_pointer",
        "/path": "openapi_path_from_pointer",
    }.get(claim_path)
    if direct is not None:
        return direct
    if claim_path == "/request_schema_ref":
        return "openapi_request_schema_name_from_ref"
    parts = claim_path.strip("/").split("/")
    if (
        len(parts) == 4
        and parts[0] == "parameters"
        and parts[1] == "body"
        and parts[3] == "name"
    ):
        return "openapi_request_body_property_name_from_pointer"
    if (
        len(parts) == 4
        and parts[0] == "parameters"
        and parts[1] == "body"
        and parts[3] == "required"
        and pointer_parts is not None
        and len(pointer_parts) == 3
        and pointer_parts[:2] == ("components", "schemas")
    ):
        return "openapi_request_body_property_required_from_schema_pointer"
    if len(parts) == 3 and parts[0] == "responses" and parts[2] == "status_code":
        return "openapi_response_status_from_pointer"
    if len(parts) == 3 and parts[0] == "responses" and parts[2] == "schema_ref":
        return "openapi_schema_name_from_ref"
    return None


def _json_pointer_parts(pointer: str) -> tuple[str, ...] | None:
    if not pointer.startswith("/"):
        return None
    decoded: list[str] = []
    for segment in pointer.split("/")[1:]:
        value: list[str] = []
        index = 0
        while index < len(segment):
            character = segment[index]
            if character != "~":
                value.append(character)
                index += 1
                continue
            if index + 1 >= len(segment) or segment[index + 1] not in {"0", "1"}:
                return None
            value.append("~" if segment[index + 1] == "0" else "/")
            index += 2
        decoded.append("".join(value))
    return tuple(decoded)


def _local_openapi_schema_name(value: Any) -> str | None:
    prefix = "#/components/schemas/"
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    name = value.removeprefix(prefix)
    if not name or "/" in name:
        return None
    decoded = _json_pointer_parts(f"/{name}")
    return decoded[0] if decoded is not None else None


def _digest_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _direct_evidence_for_path(
    citations: list[SourceCitation],
    path: str,
) -> tuple[tuple[SourceCitation, ExtractionEvidenceReference], ...]:
    """Return v1 references that explicitly own one material claim path.

    Presence of a v1 reference deliberately disables legacy locator fallback
    for that same path.  A declared exact reference must have survived the
    boundary digest check before it can become ``explicit_support``.
    """

    return tuple(
        (citation, reference)
        for citation in citations
        for reference in citation.evidence
        if reference.claim_path == path
    )


def _fragment_index(evidence: EvidenceBundle, fragment_id: str) -> int:
    for index, fragment in enumerate(evidence.fragments):
        if fragment.id == fragment_id:
            return index
    raise KeyError(fragment_id)


def _source_fact_fragments_for_path(
    fragments: tuple[EvidenceFragment, ...],
    claim_path: str,
) -> tuple[EvidenceFragment, ...]:
    parts = claim_path.strip("/").split("/")
    if len(parts) == 4 and parts[0] == "parameters":
        _, _location, name, field = parts
        cells = [
            fragment
            for fragment in fragments
            if isinstance(fragment.locator, TableCellLocator)
            and fragment.precision is FragmentPrecision.EXACT
        ]
        rows_with_name = {
            (cell.locator.table_index, cell.locator.row_index)
            for cell in cells
            if _column_role(cell.locator.column_name) == "name"
            and str(cell.semantic_value) == _unescape_segment(name)
        }
        return tuple(
            cell
            for cell in cells
            if (cell.locator.table_index, cell.locator.row_index) in rows_with_name
            and _column_role(cell.locator.column_name) == field
        )
    return ()


def _column_role(column_name: str | None) -> str | None:
    lowered = (column_name or "").strip().lower()
    if any(token in lowered for token in ("name", "field", "參數", "欄位", "名稱")):
        return "name"
    if any(token in lowered for token in ("required", "mandatory", "必填")):
        return "required"
    return None


def _verification_method(fragment: EvidenceFragment) -> VerificationMethod:
    if isinstance(fragment.locator, TableCellLocator):
        return VerificationMethod.TABLE_CELL_MAPPING
    if isinstance(fragment.locator, JsonPointerLocator):
        return VerificationMethod.STRUCTURED_FIELD_PATH
    if fragment.semantic_role and fragment.semantic_role.startswith("endpoint."):
        return VerificationMethod.SOURCE_FACT_COVERAGE
    return VerificationMethod.EXACT_NORMALIZED_VALUE


def _fragment_is_applicable(
    fragment: EvidenceFragment,
    claim_kind: str,
    claim_value: Any,
    claim_path: str,
) -> bool:
    if isinstance(fragment.locator, JsonPointerLocator):
        expected = claim_value_at(claim_kind, claim_value, claim_path)
        observed = fragment.semantic_value
        if isinstance(observed, dict):
            try:
                observed = claim_value_at(claim_kind, observed, claim_path)
            except Exception:
                return False
        return _canonical_json(expected) == _canonical_json(observed)
    if isinstance(fragment.locator, TableCellLocator):
        return _column_role(fragment.locator.column_name) == claim_path.rsplit("/", 1)[-1]
    return isinstance(
        fragment.locator,
        (LineRangeLocator, PageLocator, CssSelectorLocator, XPathLocator),
    )


def _citation_locator(citation: SourceCitation):
    raw = citation.locator
    if raw is None:
        return parse_legacy_locator(None)
    if raw.startswith(("css:", "xpath:", "section:")) or "#" in raw:
        return parse_legacy_locator(raw)
    source = citation.manifest_source or ""
    return parse_legacy_locator(f"{source} {raw}".strip())


def _all_citations(plan: NormalizationPlan) -> tuple[SourceCitation, ...]:
    entries: list[Any] = [
        *plan.environments,
        *plan.endpoints,
        *plan.schemas,
        *plan.security_schemes,
        *plan.errors,
        *plan.operational,
    ]
    if plan.integration is not None:
        entries.extend(plan.integration.crypto)
        entries.extend(plan.integration.callbacks)
        entries.extend(plan.integration.field_conditions)
        entries.extend(plan.integration.test_cases)
    return tuple(
        citation for entry in entries for citation in entry.citations
    )


def _unescape_segment(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")


def _unique_diagnostics(
    diagnostics: list[BridgeDiagnostic],
) -> tuple[BridgeDiagnostic, ...]:
    unique = {
        _canonical_json(item.model_dump(mode="json")): item
        for item in diagnostics
    }
    return tuple(unique[key] for key in sorted(unique))


def _canonical_source_metadata(manifest: Manifest) -> list[dict[str, str | None]]:
    metadata: list[dict[str, str | None]] = []
    for source in manifest.local_sources:
        metadata.append(
            {
                "identity": source.relative_path,
                "kind": "file",
                "content_digest": source.sha256,
                "usability": (
                    "usable"
                    if _usable_local_source(source)
                    else source.status.value
                    if source.status is not ProcessingStatus.PENDING
                    else "unsupported"
                ),
            }
        )
    for source in manifest.url_sources:
        metadata.append(
            {
                "identity": source.url,
                "kind": "url",
                "content_digest": source.content_sha256,
                "usability": (
                    "acquired" if source.content_sha256 is not None else "unacquired"
                ),
            }
        )
    canonical_rows = {
        _canonical_json(item): item
        for item in metadata
    }
    return [canonical_rows[key] for key in sorted(canonical_rows)]


def _usable_local_source(source: LocalSource) -> bool:
    return source.supported and source.status is ProcessingStatus.PENDING


def _descriptor(
    *, kind: str, locator: str, media_type: str | None
) -> SourceDescriptor:
    digest = hashlib.sha256(f"{kind}:{locator}".encode()).hexdigest()[:20]
    return SourceDescriptor(
        id=f"source-{digest}",
        kind=kind,
        locator=locator,
        media_type=media_type,
    )


def _artifact_and_fragment(
    *,
    descriptor: SourceDescriptor,
    digest: str,
    acquired_at: datetime,
    media_type: str,
    acquisition_metadata: tuple[tuple[str, str], ...],
) -> tuple[SourceArtifact, EvidenceFragment]:
    artifact_digest = hashlib.sha256(
        f"{descriptor.id}:{digest}".encode()
    ).hexdigest()[:24]
    artifact = SourceArtifact(
        id=f"artifact-{artifact_digest}",
        source_id=descriptor.id,
        media_type=media_type,
        content_digest=digest,
        acquired_at=acquired_at,
        acquisition_metadata=acquisition_metadata,
    )
    fragment_digest = hashlib.sha256(f"{artifact.id}:whole".encode()).hexdigest()[:24]
    fragment = EvidenceFragment(
        id=f"fragment-{fragment_digest}",
        source_artifact_id=artifact.id,
        locator="whole",
        fragment_digest=digest,
    )
    return artifact, fragment
