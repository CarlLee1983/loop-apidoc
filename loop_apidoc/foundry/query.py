from __future__ import annotations

from pathlib import Path

from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.models import Asset, AssetArtifacts, Catalog, FoundryInputError

_ARTIFACT_FIELDS = frozenset(AssetArtifacts.model_fields)


def load_current_asset(project_root: Path, docset_id: str) -> Asset:
    pointer = store.load_current(project_root, docset_id)
    if pointer is None:
        raise FoundryInputError(f"no current asset for docset: {docset_id}")
    return store.load_asset(project_root, docset_id, pointer.current_asset)


def resolve_current_artifact(
    project_root: Path, docset_id: str, artifact: str
) -> Path:
    if artifact not in _ARTIFACT_FIELDS:
        raise FoundryInputError(f"unknown artifact: {artifact}")
    asset = load_current_asset(project_root, docset_id)
    rel = getattr(asset.artifacts, artifact)
    if rel is None:
        raise FoundryInputError(
            f"artifact not present in current asset: {artifact}"
        )
    return paths.asset_dir(project_root, docset_id, asset.asset_id) / rel


def list_docsets(project_root: Path) -> Catalog:
    return store.load_catalog(project_root)
