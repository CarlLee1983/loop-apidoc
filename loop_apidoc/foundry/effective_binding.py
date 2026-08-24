"""Descriptor-bound verification of one governed Effective scope and lineage.

This is a package-internal read adapter shared by the public ``query`` seam
and the pinned Effective-promotion transaction.  It accepts held governed
descriptors only; it neither opens a project path nor exposes a public API.
"""

from __future__ import annotations

from dataclasses import dataclass

from loop_apidoc.core.conformance import canonical_digest
from loop_apidoc.domain.conformance import (
    ApplicabilityEnvelope,
    CompatibilityAmendment,
    EffectiveContract,
)

from .governed import GovernedDirectory, GovernedDocset
from .models import (
    AssetStatus,
    EffectiveAsset,
    EffectiveCurrentPointer,
    EffectiveProvenance,
    FoundryInputError,
)

_MAX_EFFECTIVE_CONTRACT_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _EffectiveArtifactBytes:
    effective_contract: bytes
    compatibility_amendment: bytes
    provenance: bytes


@dataclass(frozen=True, slots=True)
class BoundEffectiveSnapshot:
    pointer: EffectiveCurrentPointer
    asset: EffectiveAsset
    contract: EffectiveContract
    amendment: CompatibilityAmendment
    provenance: EffectiveProvenance
    artifact_bytes: _EffectiveArtifactBytes


def open_effective_scope(
    governed: GovernedDocset,
    scope_digest: str,
) -> GovernedDirectory | None:
    """Open the scope before trusting its mutable current pointer."""
    try:
        return governed.open_directory(f"effective/scopes/{scope_digest}")
    except FoundryInputError as exc:
        if isinstance(exc.__cause__, FileNotFoundError):
            return None
        raise


def read_effective_pointer(
    scope: GovernedDirectory,
) -> EffectiveCurrentPointer | None:
    return scope.read_model(
        EffectiveCurrentPointer,
        "current.json",
        "effective current pointer",
        optional=True,
    )


def read_bound_effective(
    scope: GovernedDirectory,
    docset_id: str,
    target: ApplicabilityEnvelope,
    *,
    pointer: EffectiveCurrentPointer,
) -> BoundEffectiveSnapshot:
    """Materialize one pointer, asset, and artifacts through one scope descriptor."""
    scope_digest = canonical_digest(target)
    if pointer.scope_digest != scope_digest or pointer.target != target:
        raise FoundryInputError("effective current pointer target scope is stale")
    _require_safe_segment(pointer.current_asset, "effective asset id")
    with scope.open_directory(f"assets/{pointer.current_asset}") as asset_root:
        asset = asset_root.read_model(
            EffectiveAsset,
            "asset.json",
            "effective asset manifest",
        )
        assert asset is not None
        if (
            asset.effective_asset_id != pointer.current_asset
            or asset.docset_id != docset_id
            or asset.target != target
            or asset.scope_digest != scope_digest
        ):
            raise FoundryInputError("effective asset target scope is stale")
        if asset.status is not AssetStatus.APPROVED:
            raise FoundryInputError("effective current asset is not approved")
        if canonical_digest(asset) != pointer.effective_asset_digest:
            raise FoundryInputError("effective current asset digest is stale")
        if (
            pointer.base_asset_id != asset.base_asset_id
            or pointer.effective_contract_digest != asset.effective_contract_digest
            or pointer.compatibility_amendment_digest
            != asset.compatibility_amendment_digest
            or pointer.provenance_digest != asset.provenance_digest
            or pointer.artifacts != asset.artifacts
            or pointer.approved_at != asset.approved_at
            or pointer.valid_until != asset.valid_until
            or pointer.open_discrepancy_count != asset.open_discrepancy_count
            or pointer.stale_amendment_count != asset.stale_amendment_count
            or pointer.untested_material_claim_count
            != asset.untested_material_claim_count
            or pointer.unresolved_contradiction_count
            != asset.unresolved_contradiction_count
        ):
            raise FoundryInputError("effective current pointer digest is stale")
        contract_bytes = asset_root.read_bytes(
            asset.artifacts.effective_contract,
            "effective contract artifact",
            max_bytes=_MAX_EFFECTIVE_CONTRACT_BYTES,
        )
        amendment_bytes = asset_root.read_bytes(
            asset.artifacts.compatibility_amendment,
            "effective amendment artifact",
            max_bytes=_MAX_EFFECTIVE_CONTRACT_BYTES,
        )
        provenance_bytes = asset_root.read_bytes(
            asset.artifacts.provenance,
            "effective provenance artifact",
            max_bytes=_MAX_EFFECTIVE_CONTRACT_BYTES,
        )
        assert (
            contract_bytes is not None
            and amendment_bytes is not None
            and provenance_bytes is not None
        )
        try:
            contract = EffectiveContract.model_validate_json(contract_bytes)
        except ValueError as exc:
            raise FoundryInputError("effective contract artifact is invalid") from exc
        if (
            canonical_digest(contract) != asset.effective_contract_digest
            or contract.effective_contract_id != asset.effective_asset_id
            or contract.target != target
            or contract.base.asset_id != asset.base_asset_id
            or contract.base.contract_digest != asset.base_contract_digest
            or contract.applied_amendment_ids != asset.applied_amendment_ids
            or contract.valid_until != asset.valid_until
            or contract.open_discrepancy_count != asset.open_discrepancy_count
            or len(contract.stale_amendment_ids) != asset.stale_amendment_count
            or contract.untested_material_claim_count
            != asset.untested_material_claim_count
            or contract.unresolved_contradiction_count
            != asset.unresolved_contradiction_count
        ):
            raise FoundryInputError("effective contract artifact digest is stale")
        try:
            amendment = CompatibilityAmendment.model_validate_json(amendment_bytes)
            provenance = EffectiveProvenance.model_validate_json(provenance_bytes)
        except ValueError as exc:
            raise FoundryInputError(
                "effective amendment or provenance artifact is invalid"
            ) from exc
        if canonical_digest(amendment) != asset.compatibility_amendment_digest:
            raise FoundryInputError("effective amendment artifact digest is stale")
        if canonical_digest(provenance) != asset.provenance_digest:
            raise FoundryInputError("effective provenance artifact digest is stale")
        if (
            amendment.amendment_id not in asset.applied_amendment_ids
            or provenance.amendment_ids != asset.applied_amendment_ids
            or provenance.base_asset_id != asset.base_asset_id
            or provenance.base_contract_digest != asset.base_contract_digest
            or provenance.effective_contract_digest
            != asset.effective_contract_digest
        ):
            raise FoundryInputError("effective provenance lineage is stale")
        if (
            asset.base_asset_id != amendment.approval.base_asset_id
            or asset.base_contract_digest
            != amendment.approval.base_contract_digest
            or asset.approved_at != amendment.approval.approved_at
            or asset.approved_by != amendment.approval.approved_by
            or provenance.approval_id != amendment.approval.approval_id
            or provenance.assessment_digest
            != amendment.approval.assessment_digest
            or provenance.observation_bundle_digest
            != amendment.approval.observation_bundle_digest
        ):
            raise FoundryInputError("effective provenance approval lineage is stale")
        asset_root.validate()
    return BoundEffectiveSnapshot(
        pointer=pointer,
        asset=asset,
        contract=contract,
        amendment=amendment,
        provenance=provenance,
        artifact_bytes=_EffectiveArtifactBytes(
            effective_contract=contract_bytes,
            compatibility_amendment=amendment_bytes,
            provenance=provenance_bytes,
        ),
    )


def read_effective_lineage(
    scope: GovernedDirectory,
    docset_id: str,
    target: ApplicabilityEnvelope,
    current: BoundEffectiveSnapshot,
) -> tuple[CompatibilityAmendment, ...]:
    """Traverse one effective hash chain beneath the same held scope descriptor."""
    scope_digest = canonical_digest(target)
    asset_id = current.asset.supersedes
    expected_asset_digest = current.asset.supersedes_asset_digest
    visited = {current.asset.effective_asset_id}
    amendments = {current.amendment.amendment_id: current.amendment}
    while asset_id is not None:
        _require_safe_segment(asset_id, "effective asset id")
        if asset_id in visited or len(visited) >= 1000:
            raise FoundryInputError(
                "effective asset governed lineage is cyclic or too deep"
            )
        visited.add(asset_id)
        with scope.open_directory(f"assets/{asset_id}") as asset_root:
            asset = asset_root.read_model(
                EffectiveAsset,
                "asset.json",
                "effective asset manifest",
            )
            assert asset is not None
            if canonical_digest(asset) != expected_asset_digest:
                raise FoundryInputError("effective predecessor asset digest is stale")
            if (
                asset.effective_asset_id != asset_id
                or asset.docset_id != docset_id
                or asset.scope_digest != scope_digest
                or asset.target != target
            ):
                raise FoundryInputError(
                    "effective asset governed lineage has stale scope"
                )
            amendment_bytes = asset_root.read_bytes(
                asset.artifacts.compatibility_amendment,
                "effective amendment artifact",
                max_bytes=_MAX_EFFECTIVE_CONTRACT_BYTES,
            )
            assert amendment_bytes is not None
            try:
                amendment = CompatibilityAmendment.model_validate_json(amendment_bytes)
            except ValueError as exc:
                raise FoundryInputError(
                    "effective compatibility amendment is invalid"
                ) from exc
            if canonical_digest(amendment) != asset.compatibility_amendment_digest:
                raise FoundryInputError("effective amendment artifact digest is stale")
            asset_root.validate()
        existing = amendments.get(amendment.amendment_id)
        if existing is not None and existing != amendment:
            raise FoundryInputError("effective asset lineage repeats an amendment id")
        amendments[amendment.amendment_id] = amendment
        asset_id = asset.supersedes
        expected_asset_digest = asset.supersedes_asset_digest
    return tuple(amendments[key] for key in sorted(amendments))


def _require_safe_segment(value: str, label: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise FoundryInputError(f"unsafe {label}")
