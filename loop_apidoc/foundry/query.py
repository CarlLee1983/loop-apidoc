from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loop_apidoc.core.conformance import canonical_digest
from loop_apidoc.domain.conformance import (
    ApplicabilityEnvelope,
    CompatibilityAmendment,
    EffectiveContract,
)
from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.models import (
    Asset,
    AssetArtifacts,
    AssetStatus,
    Catalog,
    EffectiveAsset,
    EffectiveAssetArtifacts,
    EffectiveProvenance,
    FoundryInputError,
)

_ARTIFACT_FIELDS = frozenset(AssetArtifacts.model_fields)
_EFFECTIVE_ARTIFACT_FIELDS = frozenset(EffectiveAssetArtifacts.model_fields)
_MAX_EFFECTIVE_CONTRACT_BYTES = 16 * 1024 * 1024


def load_current_asset(project_root: Path, docset_id: str) -> Asset:
    pointer = store.load_current(project_root, docset_id)
    if pointer is None:
        raise FoundryInputError(f"no current asset for docset: {docset_id}")
    return store.load_asset(project_root, docset_id, pointer.current_asset)


def resolve_current_artifact(project_root: Path, docset_id: str, artifact: str) -> Path:
    if artifact not in _ARTIFACT_FIELDS:
        raise FoundryInputError(f"unknown artifact: {artifact}")
    asset = load_current_asset(project_root, docset_id)
    rel = getattr(asset.artifacts, artifact)
    if rel is None:
        raise FoundryInputError(f"artifact not present in current asset: {artifact}")
    return paths.asset_dir(project_root, docset_id, asset.asset_id) / rel


def list_docsets(project_root: Path) -> Catalog:
    return store.load_catalog(project_root)


def load_current_effective_asset(
    project_root: Path,
    docset_id: str,
    target: ApplicabilityEnvelope,
    *,
    now: datetime,
) -> EffectiveAsset:
    """Resolve only the pointer for the exact requested applicability envelope."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise FoundryInputError("effective current query time must include a timezone")
    asset, contract = load_bound_effective_asset(project_root, docset_id, target)
    normative_current = store.load_current(project_root, docset_id)
    if normative_current is None or normative_current.current_asset != asset.base_asset_id:
        raise FoundryInputError("effective contract base is no longer normative current")
    if asset.approved_at > now or contract.as_of > now:
        raise FoundryInputError("effective contract is not yet approved at query time")
    if asset.valid_until is not None and asset.valid_until <= now:
        raise FoundryInputError("effective contract is expired")
    return asset


def load_bound_effective_asset(
    project_root: Path,
    docset_id: str,
    target: ApplicabilityEnvelope,
) -> tuple[EffectiveAsset, EffectiveContract]:
    """Verify the exact-scope current pointer, asset, and all bounded artifacts."""
    _require_safe_segment(docset_id, "docset id")
    scope_digest = canonical_digest(target)
    pointer = store.load_effective_current(project_root, docset_id, scope_digest)
    if pointer is None:
        raise FoundryInputError(
            f"no current effective asset for docset and target scope: {docset_id}"
        )
    if pointer.scope_digest != scope_digest or pointer.target != target:
        raise FoundryInputError("effective current pointer target scope is stale")
    _require_safe_segment(pointer.current_asset, "effective asset id")
    asset = store.load_effective_asset(
        project_root, docset_id, scope_digest, pointer.current_asset
    )
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
    root = paths.effective_asset_dir(
        project_root, docset_id, scope_digest, asset.effective_asset_id
    ).resolve()
    contract_candidate = root / asset.artifacts.effective_contract
    if contract_candidate.is_symlink():
        raise FoundryInputError("effective contract artifact path is unsafe")
    contract_path = contract_candidate.resolve()
    if not contract_path.is_relative_to(root):
        raise FoundryInputError("effective contract artifact path is unsafe")
    if not contract_path.is_file():
        raise FoundryInputError("effective contract artifact is missing")
    if contract_path.stat().st_size > _MAX_EFFECTIVE_CONTRACT_BYTES:
        raise FoundryInputError("effective contract artifact exceeds size limit")
    try:
        contract = EffectiveContract.model_validate_json(
            contract_path.read_bytes()
        )
    except (OSError, ValueError) as exc:
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
    amendment_path = _bounded_effective_artifact_path(
        root, asset.artifacts.compatibility_amendment, "amendment"
    )
    provenance_path = _bounded_effective_artifact_path(
        root, asset.artifacts.provenance, "provenance"
    )
    try:
        amendment = CompatibilityAmendment.model_validate_json(
            amendment_path.read_bytes()
        )
        provenance = EffectiveProvenance.model_validate_json(
            provenance_path.read_bytes()
        )
    except (OSError, ValueError) as exc:
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
    return asset, contract


def load_bound_effective_amendments(
    project_root: Path,
    docset_id: str,
    target: ApplicabilityEnvelope,
) -> tuple[CompatibilityAmendment, ...]:
    """Load one exact-scope amendment lineage through its governed hash chain."""
    _require_safe_segment(docset_id, "docset id")
    scope_digest = canonical_digest(target)
    if store.load_effective_current(project_root, docset_id, scope_digest) is None:
        return ()
    bound_asset, _ = load_bound_effective_asset(project_root, docset_id, target)
    asset_id: str | None = bound_asset.effective_asset_id
    expected_asset_digest: str | None = canonical_digest(bound_asset)
    visited: set[str] = set()
    amendments: dict[str, CompatibilityAmendment] = {}
    while asset_id is not None:
        _require_safe_segment(asset_id, "effective asset id")
        if asset_id in visited or len(visited) >= 1000:
            raise FoundryInputError(
                "effective asset governed lineage is cyclic or too deep"
            )
        visited.add(asset_id)
        asset = store.load_effective_asset(
            project_root, docset_id, scope_digest, asset_id
        )
        if canonical_digest(asset) != expected_asset_digest:
            label = (
                "current"
                if asset_id == bound_asset.effective_asset_id
                else "predecessor"
            )
            raise FoundryInputError(f"effective {label} asset digest is stale")
        if (
            asset.effective_asset_id != asset_id
            or asset.docset_id != docset_id
            or asset.scope_digest != scope_digest
            or asset.target != target
        ):
            raise FoundryInputError(
                "effective asset governed lineage has stale scope"
            )
        root = paths.effective_asset_dir(
            project_root, docset_id, scope_digest, asset_id
        ).resolve()
        amendment_path = _bounded_effective_artifact_path(
            root, asset.artifacts.compatibility_amendment, "amendment"
        )
        try:
            amendment = CompatibilityAmendment.model_validate_json(
                amendment_path.read_bytes()
            )
        except (OSError, ValueError) as exc:
            raise FoundryInputError(
                "effective compatibility amendment is invalid"
            ) from exc
        if canonical_digest(amendment) != asset.compatibility_amendment_digest:
            raise FoundryInputError("effective amendment artifact digest is stale")
        existing = amendments.get(amendment.amendment_id)
        if existing is not None and existing != amendment:
            raise FoundryInputError(
                "effective asset lineage repeats an amendment id"
            )
        amendments[amendment.amendment_id] = amendment
        asset_id = asset.supersedes
        expected_asset_digest = asset.supersedes_asset_digest
    return tuple(amendments[key] for key in sorted(amendments))


def resolve_current_effective_artifact(
    project_root: Path,
    docset_id: str,
    target: ApplicabilityEnvelope,
    artifact: str,
    *,
    now: datetime,
) -> Path:
    if artifact not in _EFFECTIVE_ARTIFACT_FIELDS:
        raise FoundryInputError(f"unknown effective artifact: {artifact}")
    asset = load_current_effective_asset(
        project_root, docset_id, target, now=now
    )
    relative = getattr(asset.artifacts, artifact)
    root = paths.effective_asset_dir(
        project_root, docset_id, asset.scope_digest, asset.effective_asset_id
    ).resolve()
    candidate = root / relative
    if candidate.is_symlink():
        raise FoundryInputError("effective artifact path is unsafe")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise FoundryInputError("effective artifact path is unsafe or missing")
    return resolved


def _require_safe_segment(value: str, label: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise FoundryInputError(f"unsafe {label}")


def _bounded_effective_artifact_path(root: Path, relative: str, label: str) -> Path:
    candidate = root / relative
    if candidate.is_symlink():
        raise FoundryInputError(f"effective {label} artifact path is unsafe")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise FoundryInputError(
            f"effective {label} artifact path is unsafe or missing"
        )
    if resolved.stat().st_size > _MAX_EFFECTIVE_CONTRACT_BYTES:
        raise FoundryInputError(f"effective {label} artifact exceeds size limit")
    return resolved
