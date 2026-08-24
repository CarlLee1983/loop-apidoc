from __future__ import annotations

import json
from dataclasses import dataclass
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
from . import paths, store
from loop_apidoc.foundry.integrity import digest_artifact, read_verified_file
from loop_apidoc.foundry.models import (
    Asset,
    AssetArtifacts,
    AssetStatus,
    Catalog,
    CurrentPointer,
    EffectiveAsset,
    EffectiveAssetArtifacts,
    EffectiveCurrentPointer,
    EffectiveProvenance,
    FoundryCurrentStaleError,
    FoundryGovernedAssetApprovalLineageError,
    FoundryGovernedAssetNotApprovedError,
    FoundryInputError,
    FoundryPublicationError,
    Docset,
)
from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.preparation.models import PreparationReport
from loop_apidoc.validate.models import ValidationReport

_ARTIFACT_FIELDS = frozenset(AssetArtifacts.model_fields)
_EFFECTIVE_ARTIFACT_FIELDS = frozenset(EffectiveAssetArtifacts.model_fields)
_MAX_EFFECTIVE_CONTRACT_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _EffectiveArtifactBytes:
    effective_contract: bytes
    compatibility_amendment: bytes
    provenance: bytes


@dataclass(frozen=True, slots=True)
class _BoundEffectiveSnapshot:
    pointer: EffectiveCurrentPointer
    asset: EffectiveAsset
    contract: EffectiveContract
    amendment: CompatibilityAmendment
    provenance: EffectiveProvenance
    artifact_bytes: _EffectiveArtifactBytes


def load_current_asset(project_root: Path, docset_id: str) -> Asset:
    """Load the one normative current asset after verifying its full binding."""
    asset, _ = _load_bound_current(project_root, docset_id)
    return asset


def load_current_asset_optional(project_root: Path, docset_id: str) -> Asset | None:
    """Return no asset only when current is absent; malformed current fails closed."""
    _require_safe_segment(docset_id, "docset id")
    try:
        with store.open_governed_docset(project_root, docset_id) as governed:
            pointer = governed.read_model(
                CurrentPointer,
                "current.json",
                "current.json",
                optional=True,
            )
            if pointer is None:
                _verify_current_baseline_from(governed, docset_id, pointer=None)
                governed.validate()
                return None
            _, _, asset = _read_bound_current_from(
                governed,
                docset_id,
                pointer=pointer,
            )
            governed.validate()
            return asset
    except FoundryPublicationError as exc:
        raise FoundryCurrentStaleError("current governed path is unsafe") from exc
    except FoundryInputError as exc:
        if isinstance(exc.__cause__, FileNotFoundError):
            raise FoundryInputError("required file missing: docset.json") from exc
        raise


def load_current_pointer(project_root: Path, docset_id: str) -> CurrentPointer:
    """Return the verified normative pointer used by read-only CLI consumers."""
    _, pointer = _load_bound_current(project_root, docset_id)
    return pointer


def _load_bound_current(
    project_root: Path,
    docset_id: str,
    *,
    pointer: CurrentPointer | None = None,
) -> tuple[Asset, CurrentPointer]:
    _require_safe_segment(docset_id, "docset id")
    try:
        with store.open_governed_docset(project_root, docset_id) as governed:
            _, bound_pointer, asset = _read_bound_current_from(
                governed,
                docset_id,
                pointer=pointer,
            )
            governed.validate()
            return asset, bound_pointer
    except FoundryPublicationError as exc:
        raise FoundryCurrentStaleError("current governed path is unsafe") from exc


def _read_bound_current_from(
    governed: store.GovernedDocset,
    docset_id: str,
    *,
    pointer: CurrentPointer | None = None,
) -> tuple[Docset, CurrentPointer, Asset]:
    """Read a fully bound normative current release from held descriptors."""
    if pointer is None:
        pointer = governed.read_model(
            CurrentPointer,
            "current.json",
            "current.json",
            optional=True,
        )
        if pointer is None:
            raise FoundryCurrentStaleError(
                f"no current asset for docset: {docset_id}"
            )
    docset, _ = _verify_current_baseline_from(
        governed,
        docset_id,
        pointer=pointer,
    )
    if pointer.docset_id != docset_id:
        raise FoundryCurrentStaleError("current pointer docset is stale")
    _require_safe_segment(pointer.current_asset, "asset id")
    try:
        asset_root = governed.open_directory(f"assets/{pointer.current_asset}")
    except FoundryInputError as exc:
        if isinstance(exc.__cause__, FileNotFoundError):
            raise FoundryCurrentStaleError("current asset identity is stale") from exc
        raise FoundryInputError("unsafe artifact path: current asset") from exc
    with asset_root:
        asset = asset_root.read_model(Asset, "asset.json", "asset.json")
        assert asset is not None
        if asset.asset_id != pointer.current_asset or asset.docset_id != docset_id:
            raise FoundryCurrentStaleError("current asset identity is stale")
        if (
            asset.status is not AssetStatus.APPROVED
            or pointer.status is not AssetStatus.APPROVED
        ):
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
        _verify_normative_artifacts_from(asset_root, asset)
        asset_root.validate()
    return docset, pointer, asset


def _verify_current_baseline_from(
    governed: store.GovernedDocset,
    docset_id: str,
    *,
    pointer: CurrentPointer | None,
    docset: Docset | None = None,
    catalog: Catalog | None = None,
) -> tuple[Docset, Catalog]:
    """Validate current-head cross bindings from the same governed namespace."""
    if docset is None:
        docset = governed.read_model(Docset, "docset.json", "docset.json")
        assert docset is not None
    if docset.docset_id != docset_id:
        raise FoundryCurrentStaleError("governance docset identity is stale")
    if catalog is None:
        catalog = governed.read_api_model(Catalog, "catalog.json", "catalog.json")
        assert catalog is not None
    matching_entries = [
        entry for entry in catalog.docsets if entry.docset_id == docset_id
    ]
    if len(matching_entries) != 1:
        raise FoundryCurrentStaleError("current catalog entry is not unique")
    entry = matching_entries[0]
    if (
        entry.title != docset.title
        or entry.provider != docset.provider
        or entry.product != docset.product
    ):
        raise FoundryCurrentStaleError("current catalog summary is stale")
    if pointer is None:
        if docset.current_asset is not None:
            raise FoundryCurrentStaleError("current pointer is missing")
        if entry.current_asset is not None:
            raise FoundryCurrentStaleError("current catalog head is stale")
        return docset, catalog
    if docset.current_asset != pointer.current_asset:
        raise FoundryCurrentStaleError("current docset head is stale")
    if entry.current_asset != pointer.current_asset:
        raise FoundryCurrentStaleError("current catalog head is stale")
    return docset, catalog


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


def _verify_normative_artifacts_from(
    asset_root: store.GovernedDirectory,
    asset: Asset,
) -> None:
    """Verify all normative bindings through one held asset descriptor."""
    for artifact in _ARTIFACT_FIELDS:
        relative = getattr(asset.artifacts, artifact)
        if relative is None:
            continue
        kind = getattr(asset.artifact_kinds, artifact)
        expected_digest = getattr(asset.artifact_digests, artifact)
        if kind is None or expected_digest is None:
            raise FoundryInputError(f"artifact binding is incomplete: {artifact}")
        try:
            actual_digest = asset_root.digest_artifact(relative, kind, artifact)
        except FoundryInputError as exc:
            message = str(exc)
            if "artifact digest is stale" in message:
                raise
            if "path is unsafe" in message or "unsafe governance relative path" in message:
                raise FoundryInputError(f"unsafe artifact path: {artifact}") from exc
            raise
        if actual_digest != expected_digest:
            raise FoundryInputError(f"artifact digest is stale: {artifact}")


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
    return _load_current_effective_snapshot(
        project_root,
        docset_id,
        target,
        now=now,
    ).asset


def load_bound_effective_asset(
    project_root: Path,
    docset_id: str,
    target: ApplicabilityEnvelope,
) -> tuple[EffectiveAsset, EffectiveContract]:
    """Verify the exact-scope current pointer, asset, and all bounded artifacts."""
    _require_safe_segment(docset_id, "docset id")
    scope_digest = canonical_digest(target)
    try:
        with store.open_governed_docset(project_root, docset_id) as governed:
            scope = _open_effective_scope(governed, scope_digest)
            if scope is None:
                raise FoundryInputError(
                    "no current effective asset for docset and target scope: "
                    f"{docset_id}"
                )
            with scope:
                pointer = _read_effective_pointer_from(scope)
                if pointer is None:
                    raise FoundryInputError(
                        "no current effective asset for docset and target scope: "
                        f"{docset_id}"
                    )
                snapshot = _read_bound_effective_from(
                    scope,
                    docset_id,
                    target,
                    pointer=pointer,
                )
                scope.validate()
            governed.validate()
    except FoundryPublicationError as exc:
        raise FoundryInputError("effective governed path is unsafe") from exc
    return snapshot.asset, snapshot.contract


def load_bound_effective_amendments(
    project_root: Path,
    docset_id: str,
    target: ApplicabilityEnvelope,
) -> tuple[CompatibilityAmendment, ...]:
    """Load one exact-scope amendment lineage through its governed hash chain."""
    _require_safe_segment(docset_id, "docset id")
    scope_digest = canonical_digest(target)
    try:
        with store.open_governed_docset(project_root, docset_id) as governed:
            scope = _open_effective_scope(governed, scope_digest)
            if scope is None:
                governed.validate()
                return ()
            with scope:
                pointer = _read_effective_pointer_from(scope)
                if pointer is None:
                    scope.validate()
                    governed.validate()
                    return ()
                current = _read_bound_effective_from(
                    scope,
                    docset_id,
                    target,
                    pointer=pointer,
                )
                amendments = _read_effective_lineage_from(
                    scope,
                    docset_id,
                    target,
                    current,
                )
                scope.validate()
            governed.validate()
            return amendments
    except FoundryPublicationError as exc:
        raise FoundryInputError("effective governed path is unsafe") from exc


def read_current_effective_artifact(
    project_root: Path,
    docset_id: str,
    target: ApplicabilityEnvelope,
    artifact: str,
    *,
    now: datetime,
) -> bytes:
    """Return a verified, immutable byte snapshot of one Effective artifact.

    Returning the canonical ``Path`` after descriptor-pinned verification
    would let a later namespace replacement redirect the caller's read.  The
    snapshot deliberately keeps the verified bytes, not the retargetable
    filesystem location.
    """
    if artifact not in _EFFECTIVE_ARTIFACT_FIELDS:
        raise FoundryInputError(f"unknown effective artifact: {artifact}")
    snapshot = _load_current_effective_snapshot(
        project_root,
        docset_id,
        target,
        now=now,
    )
    return getattr(snapshot.artifact_bytes, artifact)


def _load_current_effective_snapshot(
    project_root: Path,
    docset_id: str,
    target: ApplicabilityEnvelope,
    *,
    now: datetime,
) -> _BoundEffectiveSnapshot:
    """Read one Effective release and normative base through one held docset."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise FoundryInputError("effective current query time must include a timezone")
    _require_safe_segment(docset_id, "docset id")
    scope_digest = canonical_digest(target)
    try:
        with store.open_governed_docset(project_root, docset_id) as governed:
            scope = _open_effective_scope(governed, scope_digest)
            if scope is None:
                raise FoundryInputError(
                    "no current effective asset for docset and target scope: "
                    f"{docset_id}"
                )
            with scope:
                pointer = _read_effective_pointer_from(scope)
                if pointer is None:
                    raise FoundryInputError(
                        "no current effective asset for docset and target scope: "
                        f"{docset_id}"
                    )
                snapshot = _read_bound_effective_from(
                    scope,
                    docset_id,
                    target,
                    pointer=pointer,
                )
                try:
                    _, _, normative_current = _read_bound_current_from(
                        governed,
                        docset_id,
                    )
                except FoundryCurrentStaleError as exc:
                    raise FoundryInputError(
                        "effective contract base is no longer normative current"
                    ) from exc
                if normative_current.asset_id != snapshot.asset.base_asset_id:
                    raise FoundryInputError(
                        "effective contract base is no longer normative current"
                    )
                scope.validate()
            governed.validate()
    except FoundryPublicationError as exc:
        raise FoundryInputError("effective governed path is unsafe") from exc
    if snapshot.asset.approved_at > now or snapshot.contract.as_of > now:
        raise FoundryInputError("effective contract is not yet approved at query time")
    if snapshot.asset.valid_until is not None and snapshot.asset.valid_until <= now:
        raise FoundryInputError("effective contract is expired")
    return snapshot


def _open_effective_scope(
    governed: store.GovernedDocset,
    scope_digest: str,
) -> store.GovernedDirectory | None:
    """Open the scope before trusting its mutable current pointer."""
    try:
        return governed.open_directory(f"effective/scopes/{scope_digest}")
    except FoundryInputError as exc:
        if isinstance(exc.__cause__, FileNotFoundError):
            return None
        raise


def _read_effective_pointer_from(
    scope: store.GovernedDirectory,
) -> EffectiveCurrentPointer | None:
    return scope.read_model(
        EffectiveCurrentPointer,
        "current.json",
        "effective current pointer",
        optional=True,
    )


def _read_bound_effective_from(
    scope: store.GovernedDirectory,
    docset_id: str,
    target: ApplicabilityEnvelope,
    *,
    pointer: EffectiveCurrentPointer,
) -> _BoundEffectiveSnapshot:
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
    return _BoundEffectiveSnapshot(
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


def _read_effective_lineage_from(
    scope: store.GovernedDirectory,
    docset_id: str,
    target: ApplicabilityEnvelope,
    current: _BoundEffectiveSnapshot,
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
