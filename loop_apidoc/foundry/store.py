"""Foundry transaction policy and model persistence facade.

Descriptor-level filesystem operations live in :mod:`foundry.descriptor_io` and
pinned namespace views live in :mod:`foundry.governed`. They are re-exported
here because existing Foundry workflows use this module as their persistence
port.
"""

from __future__ import annotations

import errno
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from . import paths
from .descriptor_io import (
    _atomic_write_model_relative,
    _directory_open_flags,
    _open_directory,
    _rename_noreplace,
    entry_identity_relative,
)
from .descriptor_io import (  # noqa: F401 - store is the legacy persistence facade
    ImmutableEntryPublication,
    HeadSnapshot,
    _atomic_write_bytes_relative,
    _open_relative_parent,
    copy_tree_to_directory,
    copy_tree_to_owned_directory,
    create_owned_directory_relative,
    digest_artifact_relative,
    directory_fd_path,
    ensure_directory_relative,
    move_owned_directory_relative,
    open_directory_relative,
    read_bytes_relative,
    read_head_relative,
    read_head_model_snapshot_relative,
    read_head_snapshot_relative,
    read_model_relative,
    remove_owned_entry_relative,
    restore_head_relative,
    validate_directory_relative,
    validate_head_snapshot_relative,
    write_model_relative,
    write_once_model_relative,
)
from .governed import (
    _normalise_project_root,
    _open_governance_directories,
    _validate_governance_ancestors,
    open_governed_docset,
    validate_catalog_namespace,
)
from .governed import (  # noqa: F401 - store is the legacy persistence facade
    GovernedDirectory,
    GovernedDocset,
    open_pinned_governed_docset,
    validate_governance_namespace,
)
from .models import (
    Asset,
    Catalog,
    CatalogDocsetEntry,
    CurrentPointer,
    Docset,
    EffectiveAsset,
    EffectiveCurrentPointer,
    FeedbackCase,
    FoundryGovernedAssetApprovalLineageError,
    FoundryInputError,
    FoundryPublicationError,
)

_ModelT = TypeVar("_ModelT", bound=BaseModel)


@dataclass
class GovernanceTransaction:
    """Held global-catalog and per-docset locks for one publication transaction."""

    project_root: Path
    docset_id: str
    lock_path: Path
    root_fd: int
    api_fd: int
    docset_fd: int
    assets_fd: int
    _owned_fds: tuple[int, ...]
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        try:
            # Lock cleanup is descriptor-relative.  Publication paths perform
            # their namespace validation before committing; an error path must
            # still be able to release its held locks after a hostile rename.
            os.rmdir(".governance.lock", dir_fd=self.docset_fd)
            os.rmdir(".catalog-governance.lock", dir_fd=self.api_fd)
        except OSError as exc:
            raise FoundryPublicationError(
                "governance transaction lock cleanup failed at "
                f"{self.lock_path}; rollback remains locked and the stale lock "
                "must be removed only after verifying no approval is active"
            ) from exc
        except BaseException:
            raise
        else:
            self._close_fds()
        self._closed = True

    def force_close(self) -> None:
        """Best-effort final lock removal after rollback has completed."""
        if self._closed:
            return
        try:
            try:
                os.rmdir(".governance.lock", dir_fd=self.docset_fd)
            except FileNotFoundError:
                pass
            os.rmdir(".catalog-governance.lock", dir_fd=self.api_fd)
        except OSError as exc:
            raise FoundryPublicationError(
                "governance transaction lock remains at "
                f"{self.lock_path}; verify no approval is active and remove it "
                "before retrying"
            ) from exc
        self._close_fds()
        self._closed = True

    def abandon(self) -> None:
        """Close descriptors while retaining the lock as a recovery guard."""
        if self._closed:
            return
        self._close_fds()
        self._closed = True

    def own_fd(self, descriptor: int) -> None:
        """Attach a nested pinned directory to this transaction's lifetime."""
        if self._closed:
            os.close(descriptor)
            raise FoundryPublicationError("governance transaction is closed")
        self._owned_fds = (*self._owned_fds, descriptor)

    def _close_fds(self) -> None:
        for descriptor in reversed(self._owned_fds):
            try:
                os.close(descriptor)
            except OSError:
                pass


@dataclass
class CatalogTransaction:
    """Held global catalog lock for registration before a docset exists."""

    project_root: Path
    root_fd: int
    foundry_fd: int
    api_fd: int
    docsets_fd: int
    _owned_fds: tuple[int, ...]
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        validate_catalog_namespace(
            self.project_root,
            root_fd=self.root_fd,
            foundry_fd=self.foundry_fd,
            api_fd=self.api_fd,
            docsets_fd=self.docsets_fd,
        )
        try:
            os.rmdir(".catalog-governance.lock", dir_fd=self.api_fd)
        except OSError as exc:
            raise FoundryPublicationError(
                "catalog governance lock cleanup failed; verify no publication "
                "is active before removing the stale lock"
            ) from exc
        self._close_fds()
        self._closed = True

    def force_close(self) -> None:
        if self._closed:
            return
        try:
            os.rmdir(".catalog-governance.lock", dir_fd=self.api_fd)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise FoundryPublicationError(
                "catalog governance lock remains; verify no publication is active "
                "before removing the stale lock"
            ) from exc
        self._close_fds()
        self._closed = True

    def abandon(self) -> None:
        if self._closed:
            return
        self._close_fds()
        self._closed = True

    def _close_fds(self) -> None:
        for descriptor in reversed(self._owned_fds):
            try:
                os.close(descriptor)
            except OSError:
                pass


def begin_catalog_transaction(project_root: Path) -> CatalogTransaction:
    """Acquire the global catalog lock even when the docset does not yet exist."""
    absolute_root = Path(os.path.abspath(os.fspath(project_root)))
    if absolute_root.is_symlink():
        raise FoundryInputError("project root is unsafe")
    absolute_root.mkdir(parents=True, exist_ok=True)
    project_root = _normalise_project_root(project_root)
    if not project_root.is_dir():
        raise FoundryInputError("project root is unsafe")
    root_fd = foundry_fd = api_fd = docsets_fd = -1
    try:
        root_fd = _open_directory(project_root)
        parent_fd = root_fd
        opened: list[int] = []
        for component in (paths.FOUNDRY_DIR, paths.API_DIR, "docsets"):
            try:
                descriptor = _open_directory(component, parent_fd=parent_fd)
            except FileNotFoundError:
                os.mkdir(component, dir_fd=parent_fd)
                os.fsync(parent_fd)
                descriptor = _open_directory(component, parent_fd=parent_fd)
            opened.append(descriptor)
            if len(opened) == 1:
                foundry_fd = descriptor
            elif len(opened) == 2:
                api_fd = descriptor
            else:
                docsets_fd = descriptor
            parent_fd = descriptor
        os.mkdir(".catalog-governance.lock", dir_fd=api_fd)
    except FileExistsError as exc:
        for descriptor in (docsets_fd, api_fd, foundry_fd, root_fd):
            if descriptor >= 0:
                os.close(descriptor)
        raise FoundryInputError("governance transaction is already in progress") from exc
    except OSError as exc:
        for descriptor in (docsets_fd, api_fd, foundry_fd, root_fd):
            if descriptor >= 0:
                os.close(descriptor)
        raise FoundryInputError("cannot acquire governance transaction lock") from exc
    return CatalogTransaction(
        project_root=project_root,
        root_fd=root_fd,
        foundry_fd=foundry_fd,
        api_fd=api_fd,
        docsets_fd=docsets_fd,
        _owned_fds=(docsets_fd, api_fd, foundry_fd, root_fd),
    )


@dataclass
class AssetPublication:
    """Ownership token for a newly renamed immutable asset root."""

    owned_root: bool = False
    identity: tuple[int, int] | None = None


def begin_governance_transaction(
    project_root: Path, docset_id: str, *, create_assets: bool = True
) -> GovernanceTransaction:
    """Acquire catalog and docset locks before reading or writing governed heads."""
    if (
        not docset_id
        or docset_id in {".", ".."}
        or "/" in docset_id
        or "\\" in docset_id
    ):
        raise FoundryInputError("unsafe docset id")
    project_root = _normalise_project_root(project_root)
    _validate_governance_ancestors(project_root, docset_id)
    lock_path = paths.docset_dir(project_root, docset_id) / ".governance.lock"
    root_fd = api_fd = docset_fd = assets_fd = -1
    catalog_lock_owned = False
    try:
        root_fd, api_fd, docset_fd, assets_fd = _open_governance_directories(
            project_root, docset_id, create_assets=create_assets
        )
        os.mkdir(".catalog-governance.lock", dir_fd=api_fd)
        catalog_lock_owned = True
        os.mkdir(".governance.lock", dir_fd=docset_fd)
    except FileExistsError as exc:
        if catalog_lock_owned:
            try:
                os.rmdir(".catalog-governance.lock", dir_fd=api_fd)
            except OSError:
                pass
        for descriptor in (assets_fd, docset_fd, api_fd, root_fd):
            if descriptor >= 0:
                os.close(descriptor)
        raise FoundryInputError("governance transaction is already in progress") from exc
    except OSError as exc:
        if catalog_lock_owned:
            try:
                os.rmdir(".catalog-governance.lock", dir_fd=api_fd)
            except OSError:
                pass
        for descriptor in (assets_fd, docset_fd, api_fd, root_fd):
            if descriptor >= 0:
                os.close(descriptor)
        if isinstance(exc, FileNotFoundError):
            raise FoundryInputError("required file missing: docset.json") from exc
        raise FoundryInputError("cannot acquire governance transaction lock") from exc
    return GovernanceTransaction(
        project_root=project_root,
        docset_id=docset_id,
        lock_path=lock_path,
        root_fd=root_fd,
        api_fd=api_fd,
        docset_fd=docset_fd,
        assets_fd=assets_fd,
        _owned_fds=tuple(
            descriptor
            for descriptor in (assets_fd, docset_fd, api_fd, root_fd)
            if descriptor >= 0
        ),
    )


def _write_model(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def _atomic_write_model(path: Path, model: BaseModel, *, prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=prefix, dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(model.model_dump_json(indent=2))
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


def _read_model(model: type[_ModelT], path: Path, label: str) -> _ModelT:
    if path.is_symlink():
        raise FoundryInputError(f"{label} path is unsafe")
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


def save_catalog(
    project_root: Path,
    catalog: Catalog,
    *,
    parent_fd: int | None = None,
    outcome: HeadSnapshot | None = None,
) -> None:
    if parent_fd is None:
        _write_model(paths.catalog_path(project_root), catalog)
    else:
        _atomic_write_model_relative(
            parent_fd,
            "catalog.json",
            catalog,
            prefix=".catalog-",
            outcome=outcome,
        )


def load_docset(project_root: Path, docset_id: str) -> Docset:
    return _read_model(
        Docset, paths.docset_manifest_path(project_root, docset_id), "docset.json"
    )


def save_docset(
    project_root: Path,
    docset: Docset,
    *,
    parent_fd: int | None = None,
    outcome: HeadSnapshot | None = None,
) -> None:
    if parent_fd is None:
        _write_model(paths.docset_manifest_path(project_root, docset.docset_id), docset)
    else:
        _atomic_write_model_relative(
            parent_fd,
            "docset.json",
            docset,
            prefix=".docset-",
            outcome=outcome,
        )


def load_asset(project_root: Path, docset_id: str, asset_id: str) -> Asset:
    try:
        return _read_model(
            Asset,
            paths.asset_manifest_path(project_root, docset_id, asset_id),
            "asset.json",
        )
    except FoundryInputError as exc:
        cause = exc.__cause__
        if isinstance(cause, ValidationError):
            for error in cause.errors():
                payload = error.get("input")
                if (
                    isinstance(payload, dict)
                    and payload.get("status") == "approved"
                    and not str(payload.get("approved_by") or "").strip()
                ):
                    raise FoundryGovernedAssetApprovalLineageError(
                        "governed asset approval lineage is missing"
                    ) from exc
        raise


def save_asset(project_root: Path, asset: Asset) -> None:
    save_asset_at(paths.asset_dir(project_root, asset.docset_id, asset.asset_id), asset)


def save_asset_at(asset_root: Path, asset: Asset) -> None:
    """Write an asset manifest into a complete or staged asset root."""
    _write_model(asset_root / "asset.json", asset)


def publish_asset(
    staged_root: Path,
    asset_root: Path,
    *,
    outcome: AssetPublication | None = None,
    parent_fd: int | None = None,
    expected_identity: tuple[int, int] | None = None,
) -> AssetPublication:
    """Publish a fully materialized asset root without replacing existing state."""
    publication = outcome or AssetPublication()
    if expected_identity is not None:
        publication.identity = expected_identity
    if parent_fd is None:
        if staged_root.is_symlink() or not staged_root.is_dir():
            raise FoundryInputError("staged asset root is unsafe")
        if asset_root.exists() or asset_root.is_symlink():
            raise FoundryInputError("asset root already exists")
    else:
        staged_metadata = os.stat(
            staged_root.name, dir_fd=parent_fd, follow_symlinks=False
        )
        if not stat.S_ISDIR(staged_metadata.st_mode):
            raise FoundryInputError("staged asset root is unsafe")
        if entry_identity_relative(parent_fd, asset_root.name) is not None:
            raise FoundryInputError("asset root already exists")
    if parent_fd is not None and expected_identity is not None:
        if entry_identity_relative(parent_fd, staged_root.name) != expected_identity:
            raise FoundryPublicationError("staged asset identity changed")
    if parent_fd is None:
        asset_root.parent.mkdir(parents=True, exist_ok=True)
        if asset_root.parent.is_symlink() or not asset_root.parent.is_dir():
            raise FoundryInputError("asset root parent is unsafe")
    if parent_fd is None and (asset_root.exists() or asset_root.is_symlink()):
        raise FoundryInputError("asset root already exists")
    try:
        _rename_noreplace(staged_root, asset_root, parent_fd=parent_fd)
    except OSError as exc:
        raise FoundryInputError("asset root publication failed") from exc
    publication.owned_root = True
    identity_parent_fd = parent_fd
    close_identity_parent = False
    if identity_parent_fd is None:
        identity_parent_fd = os.open(asset_root.parent, _directory_open_flags())
        close_identity_parent = True
    try:
        published_identity = entry_identity_relative(
            identity_parent_fd, asset_root.name
        )
    finally:
        if close_identity_parent:
            os.close(identity_parent_fd)
    if published_identity is None:
        raise OSError(errno.ENOENT, "published asset identity is unavailable")
    if expected_identity is not None and published_identity != expected_identity:
        raise FoundryPublicationError("published asset identity changed")
    publication.identity = published_identity
    try:
        if parent_fd is not None:
            os.fsync(parent_fd)
        else:
            descriptor = os.open(asset_root.parent, _directory_open_flags())
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except OSError:
        # The root has already been renamed. Surface inability to verify or
        # fsync the parent so approval can restore heads and remove this exact
        # newly published root before a retry.
        raise
    return publication


def load_current(project_root: Path, docset_id: str) -> CurrentPointer | None:
    path = paths.current_path(project_root, docset_id)
    if not path.is_file():
        return None
    return _read_model(CurrentPointer, path, "current.json")


def save_current(
    project_root: Path,
    docset_id: str,
    pointer: CurrentPointer,
    *,
    parent_fd: int | None = None,
    outcome: HeadSnapshot | None = None,
) -> None:
    """Atomically publish the normative current pointer."""
    if parent_fd is None:
        _atomic_write_model(
            paths.current_path(project_root, docset_id), pointer, prefix=".current-"
        )
    else:
        _atomic_write_model_relative(
            parent_fd,
            "current.json",
            pointer,
            prefix=".current-",
            outcome=outcome,
        )


def load_review_decision_bytes(
    project_root: Path,
    docset_id: str,
    run_id: str,
) -> bytes | None:
    """Read candidate-local review bytes without importing review-owned models."""
    path = paths.candidate_review_decision_path(project_root, docset_id, run_id)
    if not path.is_file():
        return None
    if path.is_symlink():
        raise FoundryInputError("review/decision.json path is unsafe")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise FoundryInputError(
            f"cannot read review/decision.json: {str(exc)[:200]}"
        ) from exc


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
    with open_governed_docset(project_root, docset_id) as governed:
        case = governed.read_model(
            FeedbackCase,
            f"feedback/cases/{case_id}/case.json",
            "feedback case manifest",
        )
        governed.validate()
    assert case is not None
    return case


def load_effective_asset(
    project_root: Path, docset_id: str, scope_digest: str, asset_id: str
) -> EffectiveAsset:
    with open_governed_docset(project_root, docset_id) as governed:
        asset = governed.read_model(
            EffectiveAsset,
            f"effective/scopes/{scope_digest}/assets/{asset_id}/asset.json",
            "effective asset manifest",
        )
        governed.validate()
    assert asset is not None
    return asset


def load_effective_current(
    project_root: Path, docset_id: str, scope_digest: str
) -> EffectiveCurrentPointer | None:
    with open_governed_docset(project_root, docset_id) as governed:
        pointer = governed.read_model(
            EffectiveCurrentPointer,
            f"effective/scopes/{scope_digest}/current.json",
            "effective current pointer",
            optional=True,
        )
        governed.validate()
    return pointer


def save_effective_current(
    project_root: Path,
    docset_id: str,
    scope_digest: str,
    pointer: EffectiveCurrentPointer,
    *,
    parent_fd: int | None = None,
    scope_parent_fd: int | None = None,
    outcome: HeadSnapshot | None = None,
) -> None:
    """Atomically publish the externally consumed scope-specific pointer."""
    if scope_parent_fd is not None:
        _atomic_write_model_relative(
            scope_parent_fd,
            "current.json",
            pointer,
            prefix=".current-",
            outcome=outcome,
        )
    elif parent_fd is None:
        # A caller without a held transaction still must not re-resolve a
        # pathname below .foundry: a scope directory can be replaced after a
        # successful lstat()/resolve() check. Traverse from the pinned docset
        # descriptor instead, then revalidate both descriptors after publish.
        with open_governed_docset(project_root, docset_id) as governed:
            with governed.open_directory(
                f"effective/scopes/{scope_digest}"
            ) as scope:
                governed.validate()
                scope.validate()
                snapshot = outcome or read_head_snapshot_relative(
                    scope.descriptor, "current.json"
                )
                try:
                    _atomic_write_model_relative(
                        scope.descriptor,
                        "current.json",
                        pointer,
                        prefix=".current-",
                        outcome=snapshot,
                    )
                    scope.validate()
                    governed.validate()
                except BaseException as primary:
                    try:
                        restore_head_relative(
                            scope.descriptor, "current.json", snapshot
                        )
                    except BaseException as rollback_error:
                        failure = FoundryPublicationError(
                            "effective current publication failed and recovery is "
                            f"required: {rollback_error}"
                        )
                        failure.recovery_required = True  # type: ignore[attr-defined]
                        raise failure from primary
                    raise
    else:
        _atomic_write_model_relative(
            parent_fd,
            f"effective/scopes/{scope_digest}/current.json",
            pointer,
            prefix=".current-",
            outcome=outcome,
        )


def upsert_catalog_entry(catalog: Catalog, entry: CatalogDocsetEntry) -> Catalog:
    replaced = False
    docsets: list[CatalogDocsetEntry] = []
    for existing in catalog.docsets:
        if existing.docset_id == entry.docset_id:
            if not replaced:
                docsets.append(entry)
                replaced = True
        else:
            docsets.append(existing)
    if not replaced:
        docsets.append(entry)
    return Catalog(version=catalog.version, docsets=docsets)
