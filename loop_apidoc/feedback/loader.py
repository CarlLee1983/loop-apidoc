from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import ValidationError

from loop_apidoc.domain.conformance import (
    ApplicabilityEnvelope,
    CompatibilityAmendment,
    CompatibilityAmendmentProposal,
    FeedbackAssessment,
    ObservationBundle,
)
from loop_apidoc.foundry import normative, query
from loop_apidoc.foundry.models import (
    FeedbackReviewDecision,
    FoundryInputError,
)
from loop_apidoc.feedback.erratum import ProviderErratumMetadata
from loop_apidoc.feedback.errors import FeedbackInputError
from loop_apidoc.feedback.identifiers import require_safe_identifier
from loop_apidoc.privacy import find_sensitive_value


MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_CONTRACT_BYTES = 16 * 1024 * 1024
MAX_FEEDBACK_REPORT_BYTES = 4 * 1024 * 1024
MAX_ERRATUM_METADATA_BYTES = 256 * 1024
MAX_ERRATUM_ARTIFACT_BYTES = 25 * 1024 * 1024


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
    require_safe_identifier(docset_id, "docset id")
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


def load_approved_contract(project_root: Path, docset_id: str, asset_id: str):
    """Compatibility wrapper for the Foundry-owned normative base reader."""

    try:
        return normative.load_approved_contract(project_root, docset_id, asset_id)
    except FoundryInputError as exc:
        raise FeedbackInputError(str(exc)) from exc


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
