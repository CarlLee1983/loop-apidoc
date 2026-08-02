from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from loop_apidoc.core.governance import contract_digest
from loop_apidoc.domain.claim_paths import ClaimPathError, claim_value_at
from loop_apidoc.domain.conformance import (
    ApplicabilityEnvelope,
    CompatibilityAmendment,
    CompatibilityAmendmentProposal,
    FeedbackAssessment,
    NormativeBaseBinding,
    NormativeRelease,
    ObservationBundle,
)
from loop_apidoc.domain.evidence import (
    ClaimEvidenceRelationship,
    EvidenceBundle,
    EvidenceFragment,
    fragment_digest,
    normalize_excerpt,
)
from loop_apidoc.domain.models import GroundedApiContract
from loop_apidoc.foundry import paths, query, store
from loop_apidoc.foundry.models import (
    Asset,
    AssetStatus,
    FeedbackReviewDecision,
    FoundryInputError,
)
from loop_apidoc.feedback.erratum import ProviderErratumMetadata
from loop_apidoc.privacy import find_sensitive_value


MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_CONTRACT_BYTES = 16 * 1024 * 1024
MAX_FEEDBACK_REPORT_BYTES = 4 * 1024 * 1024
MAX_ERRATUM_METADATA_BYTES = 256 * 1024
MAX_ERRATUM_ARTIFACT_BYTES = 25 * 1024 * 1024


class FeedbackInputError(ValueError):
    """A persisted feedback or normative-release input is unsafe or invalid."""


def load_observation_bundle(path: Path) -> ObservationBundle:
    raw = _bounded_read(path, MAX_BUNDLE_BYTES, "observation bundle")
    try:
        bundle = ObservationBundle.model_validate_json(raw)
    except ValidationError as exc:
        raise FeedbackInputError(
            f"observation bundle is invalid: {_safe_validation_summary(exc)}"
        ) from exc
    except ValueError as exc:
        raise FeedbackInputError("observation bundle is not valid JSON") from exc
    _reject_sensitive_model(bundle, "observation bundle")
    return bundle


def load_feedback_assessment(path: Path) -> FeedbackAssessment:
    return _load_json_model(
        FeedbackAssessment, path, MAX_FEEDBACK_REPORT_BYTES, "feedback assessment"
    )


def load_amendment_proposal(path: Path) -> CompatibilityAmendmentProposal:
    return _load_json_model(
        CompatibilityAmendmentProposal,
        path,
        MAX_FEEDBACK_REPORT_BYTES,
        "compatibility amendment proposal",
    )


def load_compatibility_amendment(path: Path) -> CompatibilityAmendment:
    return _load_json_model(
        CompatibilityAmendment,
        path,
        MAX_FEEDBACK_REPORT_BYTES,
        "compatibility amendment",
    )


def load_applicability_envelope(path: Path) -> ApplicabilityEnvelope:
    return _load_json_model(
        ApplicabilityEnvelope,
        path,
        MAX_FEEDBACK_REPORT_BYTES,
        "applicability envelope",
    )


def load_current_scope_amendments(
    project_root: Path,
    docset_id: str,
    target: ApplicabilityEnvelope,
) -> tuple[CompatibilityAmendment, ...]:
    """Load the immutable amendment lineage for one exact effective scope."""
    _require_safe_identifier(docset_id, "docset id")
    try:
        return query.load_bound_effective_amendments(
            project_root, docset_id, target
        )
    except FoundryInputError as exc:
        raise FeedbackInputError(str(exc)) from exc


def load_feedback_review_decision(path: Path) -> FeedbackReviewDecision:
    return _load_json_model(
        FeedbackReviewDecision,
        path,
        MAX_FEEDBACK_REPORT_BYTES,
        "feedback review decision",
    )


def load_provider_erratum_inputs(
    metadata_path: Path, artifact_path: Path
) -> tuple[ProviderErratumMetadata, str]:
    metadata = _load_json_model(
        ProviderErratumMetadata,
        metadata_path,
        MAX_ERRATUM_METADATA_BYTES,
        "provider erratum metadata",
    )
    artifact = _bounded_read(
        artifact_path, MAX_ERRATUM_ARTIFACT_BYTES, "provider erratum artifact"
    )
    if artifact_path.name != metadata.artifact_name:
        raise FeedbackInputError(
            "provider erratum artifact filename does not match its metadata"
        )
    digest = "sha256:" + hashlib.sha256(artifact).hexdigest()
    if digest != metadata.artifact_digest:
        raise FeedbackInputError("provider erratum artifact digest mismatch")
    return metadata, digest


def load_approved_contract(
    project_root: Path, docset_id: str, asset_id: str
) -> tuple[Asset, NormativeRelease]:
    _require_safe_identifier(docset_id, "docset id")
    _require_safe_identifier(asset_id, "asset id")
    try:
        asset = store.load_asset(project_root, docset_id, asset_id)
        docset = store.load_docset(project_root, docset_id)
    except FoundryInputError as exc:
        raise FeedbackInputError(str(exc)) from exc
    if asset.docset_id != docset_id or asset.asset_id != asset_id:
        raise FeedbackInputError("asset identity does not match the requested base release")
    if asset.status not in {AssetStatus.APPROVED, AssetStatus.SUPERSEDED}:
        raise FeedbackInputError("feedback requires an approved normative asset")
    if not asset.approved_at or not asset.approved_by:
        raise FeedbackInputError("base asset is missing approval lineage")
    contract_path = paths.asset_artifacts_dir(
        project_root, docset_id, asset_id
    ) / "core" / "contract.json"
    if contract_path.is_symlink():
        raise FeedbackInputError("Canonical Contract artifact must not be a symlink")
    raw = _bounded_read(contract_path, MAX_CONTRACT_BYTES, "Canonical Contract")
    try:
        contract = GroundedApiContract.model_validate_json(raw)
    except ValidationError as exc:
        raise FeedbackInputError(
            f"Canonical Contract artifact is invalid: {_safe_validation_summary(exc)}"
        ) from exc
    except ValueError as exc:
        raise FeedbackInputError("Canonical Contract artifact is not valid JSON") from exc
    if contract.metadata.contract_id != docset.docset_id:
        raise FeedbackInputError("Canonical Contract identity does not match the docset")
    fragments, relationships = _verify_normative_evidence(
        contract,
        evidence_path=contract_path.with_name("evidence.json"),
        relationships_path=contract_path.with_name("relationships.json"),
    )
    return asset, NormativeRelease(
        base=NormativeBaseBinding(
            docset_id=docset_id,
            asset_id=asset_id,
            contract_digest=contract_digest(contract),
        ),
        contract=contract,
        fragments=fragments,
        relationships=relationships,
    )


def _verify_normative_evidence(
    contract: GroundedApiContract,
    *,
    evidence_path: Path,
    relationships_path: Path,
) -> tuple[tuple[EvidenceFragment, ...], tuple[ClaimEvidenceRelationship, ...]]:
    evidence_raw = _bounded_read(
        evidence_path, MAX_CONTRACT_BYTES, "Canonical evidence bundle"
    )
    relationships_raw = _bounded_read(
        relationships_path, MAX_CONTRACT_BYTES, "Canonical evidence relationships"
    )
    try:
        evidence = EvidenceBundle.model_validate_json(evidence_raw)
        relationships = TypeAdapter(
            tuple[ClaimEvidenceRelationship, ...]
        ).validate_json(relationships_raw)
    except ValidationError as exc:
        raise FeedbackInputError(
            f"Canonical evidence artifacts are invalid: {_safe_validation_summary(exc)}"
        ) from exc
    except ValueError as exc:
        raise FeedbackInputError(
            "Canonical evidence artifacts are not valid JSON"
        ) from exc
    if (
        evidence.source_set_id != contract.metadata.source_set_id
        or evidence.source_set_version != contract.metadata.source_set_version
    ):
        raise FeedbackInputError(
            "Canonical evidence bundle does not match the contract source set"
        )
    fragment_ids = [fragment.id for fragment in evidence.fragments]
    relationship_ids = [relationship.id for relationship in relationships]
    if len(fragment_ids) != len(set(fragment_ids)):
        raise FeedbackInputError("Canonical evidence fragment ids must be unique")
    if len(relationship_ids) != len(set(relationship_ids)):
        raise FeedbackInputError("Canonical evidence relationship ids must be unique")
    fragments = {fragment.id: fragment for fragment in evidence.fragments}
    claims = {claim.identity: claim for claim in contract.claims}
    for fragment in evidence.fragments:
        if fragment.normalized_excerpt is not None and fragment.fragment_digest != fragment_digest(
            normalize_excerpt(fragment.normalized_excerpt)
        ):
            raise FeedbackInputError(
                f"Canonical evidence fragment digest mismatch: {fragment.id}"
            )
    for relationship in relationships:
        if relationship.fragment_id not in fragments:
            raise FeedbackInputError(
                f"Canonical relationship has unknown fragment: {relationship.id}"
            )
        claim = claims.get(relationship.claim_identity)
        if claim is None:
            raise FeedbackInputError(
                f"Canonical relationship has unknown claim: {relationship.id}"
            )
        try:
            claim_value_at(
                claim.claim_kind or "", claim.value, relationship.claim_path
            )
        except ClaimPathError as exc:
            raise FeedbackInputError(
                f"Canonical relationship has unknown claim path: {relationship.id}"
            ) from exc
    known_relationships = set(relationship_ids)
    for claim in contract.claims:
        for binding in claim.evidence:
            if (
                binding.relationship_id is not None
                and binding.relationship_id not in known_relationships
            ):
                raise FeedbackInputError(
                    f"Canonical Contract references unknown evidence relationship: {binding.relationship_id}"
                )
    return evidence.fragments, relationships


def _bounded_read(path: Path, max_bytes: int, label: str) -> bytes:
    if path.is_symlink():
        raise FeedbackInputError(f"{label} must not be a symlink")
    if not path.is_file():
        raise FeedbackInputError(f"required {label} does not exist: {path}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise FeedbackInputError(f"cannot inspect {label}: {path}") from exc
    if size > max_bytes:
        raise FeedbackInputError(f"{label} exceeds the {max_bytes}-byte limit")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise FeedbackInputError(f"cannot read {label}: {path}") from exc


def _load_json_model(model_type, path: Path, max_bytes: int, label: str):
    raw = _bounded_read(path, max_bytes, label)
    try:
        value = model_type.model_validate_json(raw)
    except ValidationError as exc:
        raise FeedbackInputError(
            f"{label} is invalid: {_safe_validation_summary(exc)}"
        ) from exc
    except ValueError as exc:
        raise FeedbackInputError(f"{label} is not valid JSON") from exc
    _reject_sensitive_model(value, label)
    return value


def _reject_sensitive_model(value, label: str) -> None:
    finding = find_sensitive_value(value.model_dump(mode="json"))
    if finding is None:
        return
    kind, path = finding
    raise FeedbackInputError(f"{label} contains raw {kind} at {path}")


def _safe_validation_summary(exc: ValidationError) -> str:
    errors = exc.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    )
    if not errors:
        return "schema mismatch"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ())) or "root"
    error_type = str(first.get("type", "schema_mismatch"))
    suffix = f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""
    return f"{location}: {error_type}{suffix}"


def _require_safe_identifier(value: str, label: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise FeedbackInputError(f"unsafe {label}")
