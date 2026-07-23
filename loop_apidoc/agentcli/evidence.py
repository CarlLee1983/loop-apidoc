"""Read-side verification for v1 exact evidence references.

This module is deliberately outside the pure extraction gate.  It uses the
fragment adapter to reopen manifest sources and verify the agent-supplied
normalized-fragment digest before a run directory is created.  Both
``verify-extraction`` and ``assemble`` call the same function.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from loop_apidoc.adapters.fragments import FragmentRequest, acquire_fragment_bundle
from loop_apidoc.domain.evidence import (
    EvidenceFragment,
    FragmentPrecision,
    SourceDescriptor,
    SourceSet,
)
from loop_apidoc.extraction.evidence import ExtractionEvidenceReference
from loop_apidoc.manifest.models import Manifest, ProcessingStatus
from loop_apidoc.domain.claim_paths import material_claim_paths
from loop_apidoc.plan.claim_projection import iter_plan_claim_projections
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.source_facts.models import FactIndex


_INVENTORY_SECTIONS = (
    "environments",
    "security_schemes",
    "endpoints",
    "schemas",
    "errors",
    "operational",
)
_INTEGRATION_SECTIONS = ("crypto", "callbacks", "field_conditions", "test_cases")


def verify_extraction_evidence(
    inventory: dict[str, Any],
    endpoints: list[tuple[str, dict[str, Any]]],
    integration: dict[str, Any] | None,
    manifest: Manifest,
    facts: FactIndex,
    generated_at: datetime,
) -> list[str]:
    """Materialize every declared v1 reference and return all mismatches.

    No reference is required yet: legacy extraction remains compatible.  Once
    an agent supplies an ``evidence[]`` item, however, its source identity,
    typed locator, materialization precision, and digest must all match the
    manifest snapshot.  This prevents a stale or hand-waved exact reference
    from reaching Core as candidate explicit support.
    """

    declared = tuple(_declared_references(inventory, endpoints, integration))
    if not declared:
        return []

    source_set, sources = _source_set(manifest)
    requests: dict[tuple[str, str], FragmentRequest] = {}
    violations: list[str] = []
    valid: list[tuple[str, ExtractionEvidenceReference, str]] = []

    for label, reference in declared:
        source_id = sources.get(reference.source)
        if source_id is None:
            violations.append(
                f"{label}: evidence source {reference.source!r} is not a usable "
                "manifest source identity"
            )
            continue
        request = FragmentRequest(source_id=source_id, locator=reference.locator)
        key = (source_id, request.locator.model_dump_json())
        requests[key] = request
        valid.append((label, reference, source_id))

    if not valid:
        return violations

    try:
        bundle = acquire_fragment_bundle(
            source_set,
            manifest,
            facts,
            tuple(requests[key] for key in sorted(requests)),
            generated_at,
        )
    except Exception as exc:
        # The source identity and locator are agent-supplied boundary data; do
        # not hide a read failure behind a generic validation later in assembly.
        return [*violations, f"evidence materialization failed: {type(exc).__name__}"]

    artifact_sources = {
        artifact.id: artifact.source_id for artifact in bundle.artifacts
    }
    for label, reference, source_id in valid:
        matches = _matching_fragments(
            bundle.fragments, artifact_sources, source_id, reference
        )
        if not matches:
            violations.append(
                f"{label}: evidence locator could not be materialized exactly "
                f"from {reference.source!r}"
            )
            continue
        if len(matches) > 1:
            violations.append(
                f"{label}: evidence locator is ambiguous in {reference.source!r}"
            )
            continue
        fragment = matches[0]
        if fragment.fragment_digest != reference.fragment_digest:
            violations.append(
                f"{label}: evidence fragment_digest is stale or mismatched for "
                f"{reference.source!r}; expected {fragment.fragment_digest}, "
                f"got {reference.fragment_digest}"
            )
    return violations


def verify_evidence_claim_paths(plan: NormalizationPlan) -> list[str]:
    """Reject v1 references that do not name a material path in their claim.

    Fragment materialization alone proves that a source snippet exists, not
    that its declared path belongs to the normalized claim it accompanies.
    The plan projection is shared with shadow, so both gates use exactly the
    same material-claim vocabulary.  This function is pure and intentionally
    runs before any run-directory writes.
    """

    violations: list[str] = []
    for projection in iter_plan_claim_projections(plan):
        paths = set(material_claim_paths(projection.claim_kind, projection.value))
        for citation in projection.entry.citations:
            for reference in citation.evidence:
                if reference.claim_path in paths:
                    continue
                violations.append(
                    f"{projection.plan_location}: evidence claim_path "
                    f"{reference.claim_path!r} does not resolve to a material "
                    f"{projection.claim_kind} claim path"
                )
    return violations


def _source_set(manifest: Manifest) -> tuple[SourceSet, dict[str, str]]:
    """Create the minimal adapter source set from presently materializable sources."""

    descriptors: list[SourceDescriptor] = []
    for source in manifest.local_sources:
        if not source.supported or source.status is not ProcessingStatus.PENDING:
            continue
        descriptors.append(
            _descriptor("file", source.relative_path, source.mime_type)
        )
    for source in manifest.url_sources:
        if source.snapshot_file is None:
            continue
        descriptors.append(_descriptor("url", source.url, None))

    ordered = tuple(sorted(
        {item.id: item for item in descriptors}.values(), key=lambda item: item.id
    ))
    version = hashlib.sha256(
        "|".join(
            f"{item.kind}:{item.locator}:{item.media_type or ''}" for item in ordered
        ).encode("utf-8")
    ).hexdigest()
    return (
        SourceSet(
            id=f"extraction-evidence-{version[:20]}",
            version=version,
            sources=ordered,
        ),
        {item.locator: item.id for item in ordered},
    )


def _descriptor(kind: str, locator: str, media_type: str | None) -> SourceDescriptor:
    digest = hashlib.sha256(f"{kind}:{locator}".encode("utf-8")).hexdigest()[:20]
    return SourceDescriptor(
        id=f"source-{digest}", kind=kind, locator=locator, media_type=media_type
    )


def _matching_fragments(
    fragments: tuple[EvidenceFragment, ...],
    artifact_sources: dict[str, str],
    source_id: str,
    reference: ExtractionEvidenceReference,
) -> tuple[EvidenceFragment, ...]:
    return tuple(
        fragment
        for fragment in fragments
        if fragment.precision is FragmentPrecision.EXACT
        and fragment.locator == reference.locator
        and artifact_sources.get(fragment.source_artifact_id) == source_id
    )


def _declared_references(
    inventory: dict[str, Any],
    endpoints: list[tuple[str, dict[str, Any]]],
    integration: dict[str, Any] | None,
) -> Iterable[tuple[str, ExtractionEvidenceReference]]:
    for section in _INVENTORY_SECTIONS:
        for index, entry in enumerate(_entries(inventory, section)):
            yield from _entry_references(
                f"inventory.json:{section}[{index}].evidence", entry
            )
            if section == "schemas":
                for field_index, field in enumerate(_entries(entry, "fields")):
                    yield from _entry_references(
                        f"inventory.json:schemas[{index}].fields[{field_index}].evidence",
                        field,
                    )
    for name, endpoint in endpoints:
        yield from _entry_references(f"{name}: evidence", endpoint)
    for section in _INTEGRATION_SECTIONS:
        for index, entry in enumerate(_entries(integration, section)):
            yield from _entry_references(
                f"integration.json:{section}[{index}].evidence", entry
            )


def _entries(payload: dict[str, Any] | None, section: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    return [item for item in payload.get(section) or () if isinstance(item, dict)]


def _entry_references(
    label: str,
    entry: dict[str, Any],
) -> Iterable[tuple[str, ExtractionEvidenceReference]]:
    for index, raw in enumerate(entry.get("evidence") or ()):
        # input_schema has already validated this shape at both callers.  The
        # defensive model_validate preserves the function's safe public seam.
        reference = ExtractionEvidenceReference.model_validate(raw)
        yield f"{label}[{index}]", reference
