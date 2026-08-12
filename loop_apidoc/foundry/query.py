from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from pathlib import PurePath

import yaml
from loop_apidoc.core.conformance import canonical_digest
from loop_apidoc.diff.loader import RunArtifacts
from loop_apidoc.domain.conformance import (
    ApplicabilityEnvelope,
    CompatibilityAmendment,
    EffectiveContract,
)
from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.integrity import digest_artifact, read_verified_file
from loop_apidoc.foundry.models import (
    Asset,
    AssetArtifacts,
    AssetStatus,
    Catalog,
    CurrentPointer,
    EffectiveAsset,
    EffectiveAssetArtifacts,
    EffectiveProvenance,
    FoundryCurrentStaleError,
    FoundryGovernedAssetApprovalLineageError,
    FoundryGovernedAssetNotApprovedError,
    FoundryInputError,
    Docset,
)
from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.preparation.models import PreparationReport
from loop_apidoc.validate.models import ValidationReport

_ARTIFACT_FIELDS = frozenset(AssetArtifacts.model_fields)
_EFFECTIVE_ARTIFACT_FIELDS = frozenset(EffectiveAssetArtifacts.model_fields)
_MAX_EFFECTIVE_CONTRACT_BYTES = 16 * 1024 * 1024


def load_current_asset(project_root: Path, docset_id: str) -> Asset:
    """Load the one normative current asset after verifying its full binding."""
    asset, _ = _load_bound_current(project_root, docset_id)
    _verify_normative_artifacts(asset, project_root)
    return asset


def load_current_asset_optional(project_root: Path, docset_id: str) -> Asset | None:
    """Return no asset only when current is absent; malformed current fails closed."""
    docset = validate_governance_baseline(project_root, docset_id)
    pointer = store.load_current(project_root, docset_id)
    if pointer is None:
        if docset.current_asset is not None:
            raise FoundryInputError("current pointer is missing")
        return None
    asset, _ = _load_bound_current(project_root, docset_id, pointer=pointer)
    _verify_normative_artifacts(asset, project_root)
    return asset


def load_current_pointer(project_root: Path, docset_id: str) -> CurrentPointer:
    """Return the verified normative pointer used by read-only CLI consumers."""
    asset, pointer = _load_bound_current(project_root, docset_id)
    _verify_normative_artifacts(asset, project_root)
    return pointer


def _load_bound_current(
    project_root: Path,
    docset_id: str,
    *,
    pointer: CurrentPointer | None = None,
) -> tuple[Asset, CurrentPointer]:
    _require_safe_segment(docset_id, "docset id")
    if pointer is None:
        pointer = store.load_current(project_root, docset_id)
    if pointer is None:
        raise FoundryCurrentStaleError(f"no current asset for docset: {docset_id}")
    try:
        validate_governance_baseline(
            project_root, docset_id, expected_current_asset=pointer.current_asset
        )
    except FoundryCurrentStaleError:
        raise
    except FoundryInputError as exc:
        raise FoundryCurrentStaleError(str(exc)) from exc
    if pointer.docset_id != docset_id:
        raise FoundryCurrentStaleError("current pointer docset is stale")
    _require_safe_segment(pointer.current_asset, "asset id")
    try:
        asset = store.load_asset(project_root, docset_id, pointer.current_asset)
    except FoundryInputError as exc:
        raise FoundryCurrentStaleError("current asset identity is stale") from exc
    if asset.asset_id != pointer.current_asset or asset.docset_id != docset_id:
        raise FoundryCurrentStaleError("current asset identity is stale")
    if asset.status is not AssetStatus.APPROVED or pointer.status is not AssetStatus.APPROVED:
        raise FoundryInputError("current asset is not approved")
    if not asset.approved_at:
        raise FoundryInputError("current asset approval time is missing")
    if not asset.approved_by or not asset.approved_by.strip():
        raise FoundryInputError("current asset approver is missing")
    if pointer.asset_digest != canonical_digest(asset):
        raise FoundryCurrentStaleError("current asset digest is stale")
    if (
        pointer.status != asset.status
        or pointer.validation != asset.validation
        or pointer.generated_at != asset.generated_at
        or pointer.approved_at != asset.approved_at
        or pointer.artifacts != asset.artifacts
        or pointer.artifact_digests != asset.artifact_digests
        or pointer.artifact_kinds != asset.artifact_kinds
        or pointer.review != asset.review
    ):
        raise FoundryCurrentStaleError("current pointer summary is stale")
    docset = store.load_docset(project_root, docset_id)
    if docset.current_asset != asset.asset_id:
        raise FoundryCurrentStaleError("current docset head is stale")
    return asset, pointer


def resolve_current_artifact(project_root: Path, docset_id: str, artifact: str) -> Path:
    if artifact not in _ARTIFACT_FIELDS:
        raise FoundryInputError(f"unknown artifact: {artifact}")
    asset = load_current_asset(project_root, docset_id)
    return _resolve_asset_artifact(project_root, docset_id, asset, artifact)


def load_governed_asset(
    project_root: Path, docset_id: str, asset_id: str
) -> Asset:
    """Load one immutable historical v1 asset with its bound artifacts."""
    _require_safe_segment(docset_id, "docset id")
    _require_safe_segment(asset_id, "asset id")
    asset = store.load_asset(project_root, docset_id, asset_id)
    if asset.asset_id != asset_id or asset.docset_id != docset_id:
        raise FoundryInputError("governed asset identity is stale")
    if asset.status not in {AssetStatus.APPROVED, AssetStatus.SUPERSEDED}:
        raise FoundryGovernedAssetNotApprovedError("governed asset is not approved")
    if not asset.approved_at or not asset.approved_by or not asset.approved_by.strip():
        raise FoundryGovernedAssetApprovalLineageError(
            "governed asset approval lineage is missing"
        )
    _verify_normative_artifacts(asset, project_root)
    return asset


def resolve_governed_artifact(
    project_root: Path, docset_id: str, asset_id: str, artifact: str
) -> Path:
    """Resolve a digest-bound artifact from an explicit immutable asset id."""
    if artifact not in _ARTIFACT_FIELDS:
        raise FoundryInputError(f"unknown artifact: {artifact}")
    asset = load_governed_asset(project_root, docset_id, asset_id)
    return _resolve_asset_artifact(project_root, docset_id, asset, artifact)


def read_current_artifact(
    project_root: Path,
    docset_id: str,
    artifact: str,
    *,
    max_bytes: int | None = None,
) -> bytes:
    """Capture bytes from the verified current artifact at point of use."""
    if artifact not in _ARTIFACT_FIELDS:
        raise FoundryInputError(f"unknown artifact: {artifact}")
    asset = load_current_asset(project_root, docset_id)
    return _read_verified_asset_artifact(
        project_root, docset_id, asset, artifact, max_bytes=max_bytes
    )


def read_governed_artifact(
    project_root: Path,
    docset_id: str,
    asset_id: str,
    artifact: str,
    *,
    max_bytes: int | None = None,
) -> bytes:
    """Capture bytes from an immutable governed artifact at point of use."""
    if artifact not in _ARTIFACT_FIELDS:
        raise FoundryInputError(f"unknown artifact: {artifact}")
    asset = load_governed_asset(project_root, docset_id, asset_id)
    return _read_verified_asset_artifact(
        project_root, docset_id, asset, artifact, max_bytes=max_bytes
    )


def load_current_baseline_artifacts(
    project_root: Path, docset_id: str
) -> tuple[RunArtifacts, dict[str, str]]:
    """Load review baseline artifacts only through the current asset bindings."""
    asset = load_current_asset(project_root, docset_id)
    if asset.artifacts.manifest is None:
        raise FoundryInputError("current baseline manifest binding is missing")

    bound: dict[str, bytes] = {}
    for name in ("openapi", "provenance", "validation", "manifest"):
        bound[name] = _read_verified_asset_artifact(
            project_root,
            docset_id,
            asset,
            name,
            max_bytes=_MAX_EFFECTIVE_CONTRACT_BYTES,
        )
    optional: dict[str, bytes | None] = {}
    for name in ("integration_contract", "preparation"):
        relative = getattr(asset.artifacts, name)
        optional[name] = (
            _read_verified_asset_artifact(
                project_root,
                docset_id,
                asset,
                name,
                max_bytes=_MAX_EFFECTIVE_CONTRACT_BYTES,
            )
            if relative is not None
            else None
        )

    try:
        openapi = yaml.safe_load(bound["openapi"])
    except yaml.YAMLError as exc:
        raise FoundryInputError("bound baseline openapi.yaml is invalid") from exc
    if not isinstance(openapi, dict):
        raise FoundryInputError("bound baseline openapi.yaml must parse to an object")
    try:
        provenance = ProvenanceDocument.model_validate_json(
            bound["provenance"]
        )
        validation = ValidationReport.model_validate_json(
            bound["validation"]
        )
        manifest = Manifest.model_validate_json(bound["manifest"])
    except ValueError as exc:
        raise FoundryInputError("bound baseline metadata is invalid") from exc

    integration: dict | None = None
    if optional["integration_contract"] is not None:
        try:
            loaded = json.loads(
                optional["integration_contract"]
            )
        except ValueError as exc:
            raise FoundryInputError("bound baseline integration contract is invalid") from exc
        if not isinstance(loaded, dict):
            raise FoundryInputError("bound baseline integration contract must be an object")
        integration = loaded

    preparation: PreparationReport | None = None
    if optional["preparation"] is not None:
        try:
            preparation = PreparationReport.model_validate_json(
                optional["preparation"]
            )
        except ValueError as exc:
            raise FoundryInputError("bound baseline preparation report is invalid") from exc

    base_root = paths.asset_artifacts_dir(project_root, docset_id, asset.asset_id)
    review_digests: dict[str, str] = {}
    for name in _ARTIFACT_FIELDS:
        relative = getattr(asset.artifacts, name)
        digest = getattr(asset.artifact_digests, name)
        if relative is None or digest is None:
            continue
        if relative.startswith("artifacts/"):
            review_digests[relative.removeprefix("artifacts/")] = digest
    return (
        RunArtifacts(
            run_dir=base_root,
            openapi=openapi,
            integration=integration,
            provenance=provenance,
            validation=validation,
            manifest=manifest,
            preparation=preparation,
        ),
        review_digests,
    )


def _resolve_asset_artifact(
    project_root: Path, docset_id: str, asset: Asset, artifact: str
) -> Path:
    rel = getattr(asset.artifacts, artifact)
    if rel is None:
        raise FoundryInputError(f"artifact not present in current asset: {artifact}")
    kind = getattr(asset.artifact_kinds, artifact)
    expected_digest = getattr(asset.artifact_digests, artifact)
    return _resolve_normative_artifact(
        project_root,
        docset_id,
        asset.asset_id,
        rel,
        kind=kind,
        expected_digest=expected_digest,
        artifact=artifact,
    )


def _read_verified_asset_artifact(
    project_root: Path,
    docset_id: str,
    asset: Asset,
    artifact: str,
    *,
    max_bytes: int | None = None,
) -> bytes:
    path = _resolve_asset_artifact(project_root, docset_id, asset, artifact)
    kind = getattr(asset.artifact_kinds, artifact)
    expected_digest = getattr(asset.artifact_digests, artifact)
    if kind != "file" or expected_digest is None:
        raise FoundryInputError(f"artifact is not a readable file: {artifact}")
    return read_verified_file(path, expected_digest, artifact, max_bytes=max_bytes)


def _verify_normative_artifacts(asset: Asset, project_root: Path) -> None:
    for artifact in _ARTIFACT_FIELDS:
        relative = getattr(asset.artifacts, artifact)
        if relative is None:
            continue
        _resolve_normative_artifact(
            project_root,
            asset.docset_id,
            asset.asset_id,
            relative,
            kind=getattr(asset.artifact_kinds, artifact),
            expected_digest=getattr(asset.artifact_digests, artifact),
            artifact=artifact,
        )


def _resolve_normative_artifact(
    project_root: Path,
    docset_id: str,
    asset_id: str,
    relative: str,
    *,
    kind: str,
    expected_digest: str,
    artifact: str,
) -> Path:
    _require_safe_segment(docset_id, "docset id")
    _require_safe_segment(asset_id, "asset id")
    try:
        relative_path = PurePath(relative)
        unsafe_relative = (
            not relative_path.parts
            or relative_path.is_absolute()
            or any(part in {"", ".", ".."} for part in relative_path.parts)
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise FoundryInputError(f"unsafe artifact path: {artifact}") from exc
    if unsafe_relative:
        raise FoundryInputError(f"unsafe artifact path: {artifact}")
    if "\\" in relative or kind not in {"file", "tree"}:
        raise FoundryInputError(f"unsafe artifact path: {artifact}")
    asset_dir = paths.asset_dir(project_root, docset_id, asset_id)
    _reject_symlinked_governed_root(project_root, asset_dir, artifact)
    root = asset_dir.resolve()
    candidate = root
    for part in relative_path.parts:
        candidate /= part
        if candidate.is_symlink():
            raise FoundryInputError(f"unsafe artifact path: {artifact}")
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise FoundryInputError(f"unsafe artifact path: {artifact}") from exc
    if not resolved.is_relative_to(root):
        raise FoundryInputError(f"unsafe artifact path: {artifact}")
    if kind == "file" and not resolved.is_file():
        raise FoundryInputError(f"artifact is missing or not a file: {artifact}")
    if kind == "tree" and not resolved.is_dir():
        raise FoundryInputError(f"artifact is missing or not a directory: {artifact}")
    actual_digest = digest_artifact(resolved, kind, artifact)
    if actual_digest != expected_digest:
        raise FoundryInputError(f"artifact digest is stale: {artifact}")
    return resolved


def _reject_symlinked_governed_root(
    project_root: Path, asset_dir: Path, artifact: str
) -> None:
    try:
        relative = asset_dir.relative_to(project_root)
    except ValueError as exc:
        raise FoundryInputError(f"unsafe artifact path: {artifact}") from exc
    current = project_root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise FoundryInputError(f"unsafe artifact path: {artifact}")


def list_docsets(project_root: Path) -> Catalog:
    return store.load_catalog(project_root)


def validate_governance_baseline(
    project_root: Path,
    docset_id: str,
    *,
    expected_current_asset: str | None = None,
) -> Docset:
    """Validate the docset/catalog/head shape before projecting a baseline."""
    _require_safe_segment(docset_id, "docset id")
    docset = store.load_docset(project_root, docset_id)
    if docset.docset_id != docset_id:
        raise FoundryInputError("governance docset identity is stale")
    catalog = store.load_catalog(project_root)
    matching_entries = [
        entry for entry in catalog.docsets if entry.docset_id == docset_id
    ]
    if len(matching_entries) != 1:
        raise FoundryInputError("current catalog entry is not unique")
    entry = matching_entries[0]
    if (
        entry.title != docset.title
        or entry.provider != docset.provider
        or entry.product != docset.product
    ):
        raise FoundryInputError("current catalog summary is stale")
    if expected_current_asset is not None and docset.current_asset != expected_current_asset:
        raise FoundryInputError("current docset head is stale")
    if expected_current_asset is not None and entry.current_asset != expected_current_asset:
        raise FoundryInputError("current catalog head is stale")
    if entry.current_asset != docset.current_asset:
        raise FoundryInputError("current catalog head is stale")
    current_path = paths.current_path(project_root, docset_id)
    if current_path.is_symlink() or (
        current_path.exists() and not current_path.is_file()
    ):
        raise FoundryInputError("current.json path is unsafe")
    if docset.current_asset is None:
        if current_path.exists():
            raise FoundryInputError("unpublished governance head is not absent")
    elif not current_path.is_file():
        raise FoundryInputError("current pointer is missing")
    return docset


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
    try:
        normative_current = load_current_asset(project_root, docset_id)
    except FoundryCurrentStaleError as exc:
        raise FoundryInputError(
            "effective contract base is no longer normative current"
        ) from exc
    if normative_current.asset_id != asset.base_asset_id:
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
