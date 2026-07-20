from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from loop_apidoc.core.models import (
    ClaimProposal,
    EvidenceBundle,
    EvidenceFragment,
    RuntimeResult,
    SourceArtifact,
    SourceDescriptor,
    SourceSet,
)
from loop_apidoc.domain.identity import (
    DomainIdentityError,
    canonical_operation_identity,
)
from loop_apidoc.domain.models import ContractMetadata, FrozenModel
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
)
from loop_apidoc.plan.models import (
    Callback,
    ContractTestCase,
    CryptoScheme,
    EndpointEntry,
    EnvironmentEntry,
    ErrorEntry,
    FieldCondition,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SchemaEntry,
    SecuritySchemeEntry,
    SourceCitation,
)
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
                replace(group[0], evidence_refs=(), diagnostics=())
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
    if not title or not title.strip() or not version or not version.strip():
        raise ShadowMetadataError(
            "shadow contract metadata requires a source-stated title and version"
        )
    return ContractMetadata(
        contract_id=f"contract-{bridge.source_set_digest[:20]}",
        title=title,
        version=version,
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
    diagnostics: tuple[BridgeDiagnostic, ...]

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.claim_kind, self.subject, self.predicate


def _proposal_candidates(
    plan: NormalizationPlan,
    bridge: BridgeInputs,
) -> list[_ProposalCandidate]:
    candidates: list[_ProposalCandidate] = []
    areas = (
        ("environments", "environment", _environment_value),
        ("endpoints", "operation", _operation_value),
        ("schemas", "schema", _schema_value),
        ("security_schemes", "security", _security_value),
        ("errors", "error", _error_value),
        ("operational", "operational_constraint", _operational_value),
    )
    for field, claim_kind, value_builder in areas:
        for index, entry in enumerate(getattr(plan, field)):
            location = f"{field}[{index}]"
            candidates.append(
                _candidate(
                    entry=entry,
                    plan_location=location,
                    claim_kind=claim_kind,
                    subject=_subject(entry, location),
                    value=value_builder(entry),
                    bridge=bridge,
                )
            )
    integration = plan.integration
    if integration is not None:
        integration_areas = (
            ("crypto", "integration_mechanic", _crypto_value),
            ("callbacks", "webhook", _callback_value),
            ("field_conditions", "integration_mechanic", _condition_value),
            ("test_cases", "integration_mechanic", _test_case_value),
        )
        for field, claim_kind, value_builder in integration_areas:
            for index, entry in enumerate(getattr(integration, field)):
                location = f"integration.{field}[{index}]"
                candidates.append(
                    _candidate(
                        entry=entry,
                        plan_location=location,
                        claim_kind=claim_kind,
                        subject=_subject(entry, location),
                        value=value_builder(entry),
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
    if status is PlanItemStatus.MISSING:
        value = None
    elif status is PlanItemStatus.UNVERIFIED:
        evidence_refs = ()
    return _ProposalCandidate(
        plan_location=plan_location,
        status=status,
        claim_kind=claim_kind,
        subject=subject,
        predicate="definition",
        value=value,
        evidence_refs=evidence_refs,
        diagnostics=diagnostics,
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
        "evidence_refs": sorted(candidate.evidence_refs),
    }
    digest = hashlib.sha256(_canonical_json(stable_input).encode()).hexdigest()[:20]
    return ClaimProposal(
        id=f"proposal-{digest}",
        claim_kind=candidate.claim_kind,
        subject=candidate.subject,
        predicate=candidate.predicate,
        value=candidate.value,
        evidence_refs=candidate.evidence_refs,
        runtime_identity=SHADOW_RUNTIME_IDENTITY,
        runtime_observation=candidate.plan_location,
    )


def _subject(entry, plan_location: str) -> str:
    if isinstance(entry, EnvironmentEntry):
        return entry.name or plan_location
    if isinstance(entry, EndpointEntry):
        if entry.method and entry.path:
            return f"{entry.method.strip().upper()} {entry.path}"
        return plan_location
    if isinstance(entry, SchemaEntry | SecuritySchemeEntry | CryptoScheme | Callback):
        return entry.name or plan_location
    if isinstance(entry, ErrorEntry):
        return entry.code or plan_location
    if isinstance(entry, OperationalEntry):
        return entry.topic or plan_location
    if isinstance(entry, FieldCondition):
        return entry.scope or plan_location
    if isinstance(entry, ContractTestCase):
        return entry.name or plan_location
    return plan_location


def _environment_value(entry: EnvironmentEntry) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", entry.name)
    if entry.base_url is not None:
        value["servers"] = [entry.base_url]
    return value


def _operation_value(entry: EndpointEntry) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for field in ("method", "path", "summary", "server"):
        _put(value, field, getattr(entry, field))
    parameters = [_parameter_value(raw) for raw in entry.parameters]
    value["parameters"] = parameters
    if entry.request and entry.request.get("schema_ref") is not None:
        value["request_schema_ref"] = entry.request["schema_ref"]
    value["responses"] = [_response_value(raw) for raw in entry.responses]
    if entry.security:
        value["security"] = list(entry.security)
    return value


def _parameter_value(raw: dict) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", raw.get("name"))
    _put(value, "location", raw.get("location") or raw.get("in"))
    if "required" in raw and raw["required"] is not None:
        value["required"] = raw["required"]
    _put(value, "schema_ref", raw.get("schema_ref"))
    return value


def _response_value(raw: dict) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "status_code", raw.get("status"))
    _put(value, "description", raw.get("description"))
    _put(value, "schema_ref", raw.get("schema_ref"))
    return value


def _schema_value(entry: SchemaEntry) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", entry.name)
    value["fields"] = [_schema_field_value(raw) for raw in entry.fields]
    return value


def _schema_field_value(raw: dict) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for field in ("name", "type", "schema_ref", "required", "condition"):
        if field in raw:
            _put(value, field, raw.get(field))
    return value


def _security_value(entry: SecuritySchemeEntry) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", entry.name)
    _put(value, "type", entry.type)
    return value


def _error_value(entry: ErrorEntry) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "code", entry.code)
    _put(value, "description", entry.meaning)
    if entry.applicable_to:
        value["applicable_to"] = [
            _canonical_operation_reference(item)
            for item in entry.applicable_to
        ]
    return value


def _operational_value(entry: OperationalEntry) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "topic", entry.topic)
    _put(value, "detail", entry.detail)
    return value


def _crypto_value(entry: CryptoScheme) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "kind", entry.purpose)
    _put(value, "name", entry.name)
    steps = [step.desc for step in entry.payload_assembly if step.desc]
    if steps:
        value["steps"] = steps
    return value


def _callback_value(entry: Callback) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", entry.name)
    _put(value, "verification", entry.verification)
    _put(value, "expected_response", entry.expected_response)
    return value


def _condition_value(entry: FieldCondition) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", entry.scope)
    steps = [entry.when] if entry.when else []
    if steps:
        value["steps"] = steps
    return value


def _test_case_value(entry: ContractTestCase) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", entry.name)
    if entry.operation_ref is not None:
        value["operation_refs"] = [
            _canonical_operation_reference(entry.operation_ref)
        ]
    return value


def _put(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        target[key] = value


def _canonical_operation_reference(value: str) -> str:
    if value.startswith("operation:"):
        return value
    method, separator, path = value.strip().partition(" ")
    if not separator:
        return value
    try:
        return canonical_operation_identity(method, path)
    except DomainIdentityError:
        return value


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
