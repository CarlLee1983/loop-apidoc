from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from loop_apidoc.foundry import paths
from loop_apidoc.foundry.models import (
    Asset,
    Catalog,
    CatalogDocsetEntry,
    CurrentPointer,
    Docset,
    EffectiveAsset,
    EffectiveCurrentPointer,
    FeedbackCase,
    FoundryInputError,
)

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _write_model(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def _read_model(model: type[_ModelT], path: Path, label: str) -> _ModelT:
    if not path.is_file():
        raise FoundryInputError(f"required file missing: {label}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FoundryInputError(f"cannot read {label}: {str(exc)[:200]}") from exc
    try:
        return model.model_validate_json(text)
    except ValidationError as exc:
        raise FoundryInputError(f"{label} is invalid: {str(exc)[:200]}") from exc
    except ValueError as exc:  # non-JSON text
        raise FoundryInputError(f"{label} is not valid JSON: {str(exc)[:200]}") from exc


def load_catalog(project_root: Path) -> Catalog:
    path = paths.catalog_path(project_root)
    if not path.is_file():
        return Catalog()
    return _read_model(Catalog, path, "catalog.json")


def save_catalog(project_root: Path, catalog: Catalog) -> None:
    _write_model(paths.catalog_path(project_root), catalog)


def load_docset(project_root: Path, docset_id: str) -> Docset:
    return _read_model(
        Docset, paths.docset_manifest_path(project_root, docset_id), "docset.json"
    )


def save_docset(project_root: Path, docset: Docset) -> None:
    _write_model(paths.docset_manifest_path(project_root, docset.docset_id), docset)


def load_asset(project_root: Path, docset_id: str, asset_id: str) -> Asset:
    return _read_model(
        Asset,
        paths.asset_manifest_path(project_root, docset_id, asset_id),
        "asset.json",
    )


def save_asset(project_root: Path, asset: Asset) -> None:
    _write_model(
        paths.asset_manifest_path(project_root, asset.docset_id, asset.asset_id), asset
    )


def load_current(project_root: Path, docset_id: str) -> CurrentPointer | None:
    path = paths.current_path(project_root, docset_id)
    if not path.is_file():
        return None
    return _read_model(CurrentPointer, path, "current.json")


def save_current(project_root: Path, docset_id: str, pointer: CurrentPointer) -> None:
    _write_model(paths.current_path(project_root, docset_id), pointer)


def load_review_decision(
    project_root: Path, docset_id: str, run_id: str
) -> object | None:
    """Load a candidate-local review decision without coupling Foundry models to review."""
    path = paths.candidate_review_decision_path(project_root, docset_id, run_id)
    if not path.is_file():
        return None
    from loop_apidoc.review.models import ReviewDecision

    return _read_model(ReviewDecision, path, "review/decision.json")


def save_review_decision(
    project_root: Path, docset_id: str, run_id: str, decision: BaseModel
) -> None:
    """The sole governance-JSON write path for candidate review decisions."""
    _write_model(
        paths.candidate_review_decision_path(project_root, docset_id, run_id), decision
    )


def load_feedback_case(
    project_root: Path, docset_id: str, case_id: str
) -> FeedbackCase:
    return _read_model(
        FeedbackCase,
        paths.feedback_case_manifest_path(project_root, docset_id, case_id),
        "feedback case manifest",
    )


def load_effective_asset(
    project_root: Path, docset_id: str, scope_digest: str, asset_id: str
) -> EffectiveAsset:
    return _read_model(
        EffectiveAsset,
        paths.effective_asset_manifest_path(
            project_root, docset_id, scope_digest, asset_id
        ),
        "effective asset manifest",
    )


def load_effective_current(
    project_root: Path, docset_id: str, scope_digest: str
) -> EffectiveCurrentPointer | None:
    path = paths.effective_current_path(project_root, docset_id, scope_digest)
    if not path.is_file():
        return None
    return _read_model(EffectiveCurrentPointer, path, "effective current pointer")


def save_effective_current(
    project_root: Path,
    docset_id: str,
    scope_digest: str,
    pointer: EffectiveCurrentPointer,
) -> None:
    """Atomically publish the externally consumed scope-specific pointer."""
    path = paths.effective_current_path(project_root, docset_id, scope_digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".current-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(pointer.model_dump_json(indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def upsert_catalog_entry(catalog: Catalog, entry: CatalogDocsetEntry) -> Catalog:
    replaced = False
    docsets: list[CatalogDocsetEntry] = []
    for existing in catalog.docsets:
        if existing.docset_id == entry.docset_id:
            docsets.append(entry)
            replaced = True
        else:
            docsets.append(existing)
    if not replaced:
        docsets.append(entry)
    return Catalog(version=catalog.version, docsets=docsets)
