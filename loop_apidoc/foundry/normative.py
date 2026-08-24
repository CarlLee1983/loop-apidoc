from __future__ import annotations

import hashlib
import os
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from loop_apidoc.core.governance import contract_digest
from loop_apidoc.domain.claim_paths import ClaimPathError, claim_value_at
from loop_apidoc.domain.conformance import NormativeBaseBinding, NormativeRelease
from loop_apidoc.domain.evidence import (
    ClaimEvidenceRelationship,
    EvidenceBundle,
    EvidenceFragment,
    fragment_digest,
    normalize_excerpt,
)
from loop_apidoc.domain.models import GroundedApiContract
from . import descriptor_io, descriptor_namespace, governed
from .models import (
    Asset,
    AssetArtifacts,
    AssetStatus,
    Docset,
    FoundryInputError,
    FoundryPublicationError,
)


MAX_CONTRACT_BYTES = 16 * 1024 * 1024


def load_approved_contract(
    project_root: Path,
    docset_id: str,
    asset_id: str,
) -> tuple[Asset, NormativeRelease]:
    """Load one approved governed base and verify its Core evidence binding."""

    asset, _, release = load_approved_contract_snapshot(
        project_root,
        docset_id,
        asset_id,
    )
    return asset, release


def load_approved_contract_snapshot(
    project_root: Path,
    docset_id: str,
    asset_id: str,
) -> tuple[Asset, Docset, NormativeRelease]:
    """Capture one approved base, docset, and Core release from held descriptors."""

    _require_safe_identifier(docset_id, "docset id")
    _require_safe_identifier(asset_id, "asset id")
    try:
        with governed.open_governed_docset(project_root, docset_id) as docset_view:
            asset, docset, release = load_approved_contract_snapshot_relative(
                docset_view.docset_fd,
                docset_id,
                asset_id,
            )
            docset_view.validate()
    except FoundryPublicationError as exc:
        raise FoundryInputError("governed normative base path is unsafe") from exc
    return asset, docset, release


def load_approved_contract_snapshot_relative(
    docset_fd: int,
    docset_id: str,
    asset_id: str,
    *,
    docset: Docset | None = None,
) -> tuple[Asset, Docset, NormativeRelease]:
    """Read one approved base from the caller's held docset descriptor.

    This is deliberately the descriptor-taking counterpart of
    :func:`load_approved_contract_snapshot`: a governed writer can verify the
    release and persist a dependent object against the same locked namespace,
    rather than reopening the docset through a path in between.
    """
    _require_safe_identifier(docset_id, "docset id")
    _require_safe_identifier(asset_id, "asset id")
    if docset is None:
        docset = descriptor_io.read_model_relative(
            docset_fd, Docset, "docset.json", "docset.json"
        )
        assert docset is not None
    if docset.docset_id != docset_id:
        raise FoundryInputError("governance docset identity is stale")
    asset_fd = -1
    try:
        try:
            asset_fd = descriptor_namespace.open_directory_relative(
                docset_fd, f"assets/{asset_id}"
            )
        except FileNotFoundError as exc:
            raise FoundryInputError("required file missing: asset.json") from exc
        try:
            asset = descriptor_io.read_model_relative(
                asset_fd, Asset, "asset.json", "asset.json"
            )
        except FoundryInputError as exc:
            if _has_missing_approval_lineage(exc):
                raise FoundryInputError("base asset is missing approval lineage") from exc
            raise
        assert asset is not None
        _verify_approved_asset_identity(asset, docset_id, asset_id)
        _verify_asset_artifacts(asset_fd, asset)
        contract_raw = _read_bound_file(
            asset_fd,
            asset,
            "core_contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
        evidence_raw = _read_bound_file(
            asset_fd,
            asset,
            "core_evidence",
            max_bytes=MAX_CONTRACT_BYTES,
        )
        relationships_raw = _read_bound_file(
            asset_fd,
            asset,
            "core_relationships",
            max_bytes=MAX_CONTRACT_BYTES,
        )
        contract = _parse_contract(contract_raw)
        if contract.metadata.contract_id != docset.docset_id:
            raise FoundryInputError(
                "Canonical Contract identity does not match the docset"
            )
        fragments, relationships = _verify_normative_evidence(
            contract,
            evidence_raw=evidence_raw,
            relationships_raw=relationships_raw,
        )
        descriptor_namespace.validate_directory_relative(
            docset_fd, f"assets/{asset_id}", asset_fd
        )
    except FoundryPublicationError:
        raise
    finally:
        if asset_fd >= 0:
            os.close(asset_fd)
    release = NormativeRelease(
        base=NormativeBaseBinding(
            docset_id=docset_id,
            asset_id=asset_id,
            contract_digest=contract_digest(contract),
        ),
        contract=contract,
        fragments=fragments,
        relationships=relationships,
    )
    return asset, docset, release


def _verify_approved_asset_identity(
    asset: Asset,
    docset_id: str,
    asset_id: str,
) -> None:
    if asset.docset_id != docset_id or asset.asset_id != asset_id:
        raise FoundryInputError("asset identity does not match the requested base release")
    if asset.status not in {AssetStatus.APPROVED, AssetStatus.SUPERSEDED}:
        raise FoundryInputError("feedback requires an approved normative asset")
    if not asset.approved_at or not asset.approved_by or not asset.approved_by.strip():
        raise FoundryInputError("base asset is missing approval lineage")


def _has_missing_approval_lineage(error: FoundryInputError) -> bool:
    """Keep the governed-base approval-lineage error stable across readers."""
    cause = error.__cause__
    if not isinstance(cause, ValidationError):
        return False
    for detail in cause.errors():
        payload = detail.get("input")
        if (
            isinstance(payload, dict)
            and payload.get("status") == AssetStatus.APPROVED.value
            and not str(payload.get("approved_by") or "").strip()
        ):
            return True
    return False


def _verify_asset_artifacts(asset_root_fd: int, asset: Asset) -> None:
    for artifact in AssetArtifacts.model_fields:
        relative = getattr(asset.artifacts, artifact)
        if relative is None:
            continue
        kind = getattr(asset.artifact_kinds, artifact)
        expected_digest = getattr(asset.artifact_digests, artifact)
        if kind is None or expected_digest is None:
            raise FoundryInputError(f"artifact binding is incomplete: {artifact}")
        actual_digest = descriptor_io.digest_artifact_relative(
            asset_root_fd, relative, kind, artifact
        )
        if actual_digest != expected_digest:
            raise FoundryInputError(f"artifact digest is stale: {artifact}")


def _read_bound_file(
    asset_root_fd: int,
    asset: Asset,
    artifact: str,
    *,
    max_bytes: int,
) -> bytes:
    relative = getattr(asset.artifacts, artifact)
    if relative is None:
        raise FoundryInputError(f"artifact not present in current asset: {artifact}")
    kind = getattr(asset.artifact_kinds, artifact)
    expected_digest = getattr(asset.artifact_digests, artifact)
    if kind != "file" or expected_digest is None:
        raise FoundryInputError(f"artifact is not a readable file: {artifact}")
    content = descriptor_io.read_bytes_relative(
        asset_root_fd,
        relative,
        artifact,
        max_bytes=max_bytes,
    )
    assert content is not None
    if hashlib.sha256(content).hexdigest() != expected_digest:
        raise FoundryInputError(f"artifact digest is stale: {artifact}")
    return content


def _parse_contract(contract_raw: bytes) -> GroundedApiContract:
    try:
        return GroundedApiContract.model_validate_json(contract_raw)
    except ValidationError as exc:
        raise FoundryInputError(
            "Canonical Contract artifact is invalid: "
            f"{_safe_validation_summary(exc)}"
        ) from exc
    except ValueError as exc:
        raise FoundryInputError("Canonical Contract artifact is not valid JSON") from exc


def _verify_normative_evidence(
    contract: GroundedApiContract,
    *,
    evidence_raw: bytes,
    relationships_raw: bytes,
) -> tuple[tuple[EvidenceFragment, ...], tuple[ClaimEvidenceRelationship, ...]]:
    try:
        evidence = EvidenceBundle.model_validate_json(evidence_raw)
        relationships = TypeAdapter(
            tuple[ClaimEvidenceRelationship, ...]
        ).validate_json(relationships_raw)
    except ValidationError as exc:
        raise FoundryInputError(
            "Canonical evidence artifacts are invalid: "
            f"{_safe_validation_summary(exc)}"
        ) from exc
    except ValueError as exc:
        raise FoundryInputError("Canonical evidence artifacts are not valid JSON") from exc
    if (
        evidence.source_set_id != contract.metadata.source_set_id
        or evidence.source_set_version != contract.metadata.source_set_version
    ):
        raise FoundryInputError(
            "Canonical evidence bundle does not match the contract source set"
        )
    fragment_ids = [fragment.id for fragment in evidence.fragments]
    relationship_ids = [relationship.id for relationship in relationships]
    if len(fragment_ids) != len(set(fragment_ids)):
        raise FoundryInputError("Canonical evidence fragment ids must be unique")
    if len(relationship_ids) != len(set(relationship_ids)):
        raise FoundryInputError("Canonical evidence relationship ids must be unique")
    fragments = {fragment.id: fragment for fragment in evidence.fragments}
    claims = {claim.identity: claim for claim in contract.claims}
    for fragment in evidence.fragments:
        if (
            fragment.normalized_excerpt is not None
            and fragment.fragment_digest
            != fragment_digest(normalize_excerpt(fragment.normalized_excerpt))
        ):
            raise FoundryInputError(
                f"Canonical evidence fragment digest mismatch: {fragment.id}"
            )
    for relationship in relationships:
        if relationship.fragment_id not in fragments:
            raise FoundryInputError(
                f"Canonical relationship has unknown fragment: {relationship.id}"
            )
        claim = claims.get(relationship.claim_identity)
        if claim is None:
            raise FoundryInputError(
                f"Canonical relationship has unknown claim: {relationship.id}"
            )
        try:
            claim_value_at(
                claim.claim_kind or "", claim.value, relationship.claim_path
            )
        except ClaimPathError as exc:
            raise FoundryInputError(
                f"Canonical relationship has unknown claim path: {relationship.id}"
            ) from exc
    known_relationships = set(relationship_ids)
    for claim in contract.claims:
        for binding in claim.evidence:
            if (
                binding.relationship_id is not None
                and binding.relationship_id not in known_relationships
            ):
                raise FoundryInputError(
                    "Canonical Contract references unknown evidence relationship: "
                    f"{binding.relationship_id}"
                )
    return evidence.fragments, relationships


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
        raise FoundryInputError(f"unsafe {label}")
