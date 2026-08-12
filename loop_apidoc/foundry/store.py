from __future__ import annotations

import ctypes
import errno
import fcntl
import os
import platform
import shutil
import stat
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePath
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
    FoundryGovernedAssetApprovalLineageError,
    FoundryInputError,
    FoundryPublicationError,
)

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _normalise_project_root(project_root: Path) -> Path:
    """Normalize ancestor aliases without accepting a symlinked project root."""
    absolute = Path(os.path.abspath(os.fspath(project_root)))
    if absolute.is_symlink():
        raise FoundryInputError("project root is unsafe")
    return Path(os.path.realpath(absolute))


def _validate_governance_ancestors(project_root: Path, docset_id: str) -> None:
    """Reject an escaped governance tree before any transaction can write."""
    if not project_root.is_dir():
        raise FoundryInputError("project root is unsafe")
    root = Path(os.path.realpath(project_root))
    chain = (
        project_root,
        project_root / paths.FOUNDRY_DIR,
        project_root / paths.FOUNDRY_DIR / paths.API_DIR,
        paths.docsets_root(project_root),
        paths.docset_dir(project_root, docset_id),
        paths.assets_dir(project_root, docset_id),
    )
    for ancestor in chain:
        if ancestor.is_symlink():
            raise FoundryInputError(f"governance ancestor is unsafe: {ancestor}")
        if ancestor.exists() and not ancestor.is_dir():
            raise FoundryInputError(f"governance ancestor is not a directory: {ancestor}")
        if ancestor.exists():
            try:
                resolved = ancestor.resolve()
            except (OSError, RuntimeError) as exc:
                raise FoundryInputError(
                    f"governance ancestor cannot be resolved: {ancestor}"
                ) from exc
            if not resolved.is_relative_to(root):
                raise FoundryInputError(f"governance ancestor escapes project root: {ancestor}")


def _open_directory(path: Path, *, parent_fd: int | None = None) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    return os.open(path, flags, dir_fd=parent_fd)


def _open_governance_directories(
    project_root: Path, docset_id: str
) -> tuple[int, int, int, int]:
    """Open the governed path one component at a time, refusing symlinks."""
    root_fd = _open_directory(project_root)
    opened = [root_fd]
    try:
        foundry_fd = _open_directory(paths.FOUNDRY_DIR, parent_fd=root_fd)
        opened.append(foundry_fd)
        api_fd = _open_directory(paths.API_DIR, parent_fd=foundry_fd)
        opened.append(api_fd)
        docsets_fd = _open_directory("docsets", parent_fd=api_fd)
        opened.append(docsets_fd)
        docset_fd = _open_directory(docset_id, parent_fd=docsets_fd)
        opened.append(docset_fd)
        try:
            assets_fd = _open_directory("assets", parent_fd=docset_fd)
        except FileNotFoundError:
            os.mkdir("assets", dir_fd=docset_fd)
            assets_fd = _open_directory("assets", parent_fd=docset_fd)
        opened.append(assets_fd)
        # The children are anchored by docset_fd/api_fd; these intermediates
        # no longer need to remain open for the transaction.
        os.close(foundry_fd)
        opened.remove(foundry_fd)
        os.close(docsets_fd)
        opened.remove(docsets_fd)
        return root_fd, api_fd, docset_fd, assets_fd
    except BaseException:
        for descriptor in reversed(opened):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


@dataclass
class GovernanceTransaction:
    """Held global-catalog and per-docset locks for one publication transaction."""

    project_root: Path
    lock_path: Path
    api_fd: int
    docset_fd: int
    assets_fd: int
    _owned_fds: tuple[int, ...]
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        try:
            # Preserve the injectable Path seam used by the workbench while
            # refusing to follow a substituted parent pathname.  The held fd
            # is authoritative whenever the pathname no longer names it.
            try:
                same_directory = os.path.samestat(
                    os.fstat(self.docset_fd), self.lock_path.parent.stat()
                )
            except (OSError, AttributeError):
                same_directory = False
            if same_directory:
                self.lock_path.rmdir()
            else:
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
        for descriptor in reversed(self._owned_fds):
            try:
                os.close(descriptor)
            except OSError:
                pass
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


def _directory_open_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _rename_noreplace(
    staged_root: Path,
    asset_root: Path,
    *,
    parent_fd: int | None = None,
) -> None:
    """Atomically rename a complete asset root only if its destination is absent.

    ``os.rename`` is intentionally not a fallback here: POSIX rename replaces an
    existing directory, including an empty foreign directory.  macOS exposes the
    required operation as ``renameatx_np(RENAME_EXCL)``; Linux exposes it as
    ``renameat2(RENAME_NOREPLACE)``.  Unsupported platforms fail closed.
    """
    if parent_fd is None and staged_root.parent != asset_root.parent:
        raise OSError(errno.EXDEV, "asset publication requires one parent directory")
    close_parent = parent_fd is None
    if parent_fd is None:
        parent_fd = os.open(asset_root.parent, _directory_open_flags())
    source_name = os.fsencode(staged_root.name)
    destination_name = os.fsencode(asset_root.name)
    try:
        if sys.platform == "darwin":
            libc = ctypes.CDLL(None, use_errno=True)
            renameatx_np = libc.renameatx_np
            renameatx_np.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            renameatx_np.restype = ctypes.c_int
            flags = 0x00000004 | 0x00000010 | 0x00000020  # EXCL | NOFOLLOW_ANY | BENEATH
            result = renameatx_np(
                parent_fd,
                source_name,
                parent_fd,
                destination_name,
                flags,
            )
        elif sys.platform.startswith("linux"):
            libc = ctypes.CDLL(None, use_errno=True)
            renameat2 = getattr(libc, "renameat2", None)
            if renameat2 is not None:
                renameat2.argtypes = [
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_uint,
                ]
                renameat2.restype = ctypes.c_int
                result = renameat2(
                    parent_fd,
                    source_name,
                    parent_fd,
                    destination_name,
                    0x00000001,  # RENAME_NOREPLACE
                )
            else:
                syscall_numbers = {
                    "x86_64": 316,
                    "aarch64": 276,
                    "armv7l": 382,
                    "ppc64le": 357,
                }
                syscall_number = syscall_numbers.get(platform.machine())
                syscall = getattr(libc, "syscall", None)
                if syscall is None or syscall_number is None:
                    raise OSError(errno.ENOTSUP, "renameat2 is unavailable")
                syscall.restype = ctypes.c_long
                result = syscall(
                    syscall_number,
                    parent_fd,
                    source_name,
                    parent_fd,
                    destination_name,
                    0x00000001,  # RENAME_NOREPLACE
                )
        else:
            raise OSError(errno.ENOTSUP, "no-replace directory rename is unavailable")
        if result != 0:
            error_number = ctypes.get_errno() or errno.EIO
            raise OSError(error_number, os.strerror(error_number))
    finally:
        if close_parent:
            os.close(parent_fd)


def begin_governance_transaction(
    project_root: Path, docset_id: str
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
            project_root, docset_id
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
        raise FoundryInputError("cannot acquire governance transaction lock") from exc
    return GovernanceTransaction(
        project_root=project_root,
        lock_path=lock_path,
        api_fd=api_fd,
        docset_fd=docset_fd,
        assets_fd=assets_fd,
        _owned_fds=(assets_fd, docset_fd, api_fd, root_fd),
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


def _atomic_write_model_relative(
    parent_fd: int, name: str, model: BaseModel, *, prefix: str
) -> None:
    """Atomically replace one governed JSON head relative to a held directory fd."""
    resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    try:
        existing = os.stat(
            basename, dir_fd=resolved_parent_fd, follow_symlinks=False
        )
    except FileNotFoundError:
        existing = None
    if existing is not None and (
        stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode)
    ):
        raise FoundryInputError(f"governance head path is unsafe: {name}")
    temporary_name = f"{prefix}{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=resolved_parent_fd,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(model.model_dump_json(indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name,
            basename,
            src_dir_fd=resolved_parent_fd,
            dst_dir_fd=resolved_parent_fd,
        )
        os.fsync(resolved_parent_fd)
    except BaseException:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.unlink(temporary_name, dir_fd=resolved_parent_fd)
        except OSError:
            pass
        raise
    finally:
        os.close(resolved_parent_fd)


def _atomic_write_bytes_relative(
    parent_fd: int, name: str, content: bytes, *, prefix: str
) -> None:
    resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    temporary_name = f"{prefix}{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=resolved_parent_fd,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name,
            basename,
            src_dir_fd=resolved_parent_fd,
            dst_dir_fd=resolved_parent_fd,
        )
        os.fsync(resolved_parent_fd)
    except BaseException:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.unlink(temporary_name, dir_fd=resolved_parent_fd)
        except OSError:
            pass
        raise
    finally:
        os.close(resolved_parent_fd)


def _open_relative_parent(parent_fd: int, name: str) -> tuple[int, str]:
    relative = PurePath(name)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\\" in name
    ):
        raise FoundryInputError(f"unsafe governance relative path: {name}")
    descriptor = os.dup(parent_fd)
    try:
        for part in relative.parts[:-1]:
            child = _open_directory(part, parent_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, relative.parts[-1]
    except BaseException:
        os.close(descriptor)
        raise


def open_directory_relative(parent_fd: int, name: str) -> int:
    """Open one existing directory beneath a pinned root without following links."""
    resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    try:
        return _open_directory(basename, parent_fd=resolved_parent_fd)
    finally:
        os.close(resolved_parent_fd)


def validate_directory_relative(
    parent_fd: int, name: str, expected_fd: int
) -> None:
    """Reject replacement of a nested directory pinned by a transaction."""
    try:
        current_fd = open_directory_relative(parent_fd, name)
    except OSError as exc:
        raise FoundryPublicationError(
            f"governance namespace changed during publication: {name}"
        ) from exc
    try:
        if not os.path.samestat(os.fstat(current_fd), os.fstat(expected_fd)):
            raise FoundryPublicationError(
                f"governance namespace changed during publication: {name}"
            )
    finally:
        os.close(current_fd)


def ensure_directory_relative(parent_fd: int, name: str) -> int:
    """Create/open a directory chain beneath a pinned root and return its fd."""
    relative = PurePath(name)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\\" in name
    ):
        raise FoundryInputError(f"unsafe governance relative path: {name}")
    descriptor = os.dup(parent_fd)
    try:
        for part in relative.parts:
            try:
                child = _open_directory(part, parent_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(part, dir_fd=descriptor)
                os.fsync(descriptor)
                child = _open_directory(part, parent_fd=descriptor)
            except OSError as exc:
                raise FoundryInputError(
                    f"unsafe governance path: {name}"
                ) from exc
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def create_owned_directory_relative(
    parent_fd: int, *, prefix: str
) -> tuple[str, int, tuple[int, int]]:
    """Create an unguessable transaction-owned directory under a pinned parent."""
    for _ in range(100):
        name = f"{prefix}{uuid.uuid4().hex}"
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        descriptor = -1
        identity: tuple[int, int] | None = None
        try:
            metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode):
                raise FoundryPublicationError(
                    "new governed staging entry is not a directory"
                )
            identity = metadata.st_dev, metadata.st_ino
            descriptor = _open_directory(name, parent_fd=parent_fd)
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != identity:
                raise FoundryPublicationError(
                    "new governed staging directory identity changed"
                )
            os.fsync(parent_fd)
            return name, descriptor, identity
        except BaseException as primary:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                if identity is None:
                    raise FoundryPublicationError(
                        "new governed staging directory ownership is unknown"
                    )
                remove_owned_entry_relative(parent_fd, name, identity)
            except BaseException as cleanup_error:
                failure = FoundryPublicationError(
                    "governed staging directory creation failed and recovery "
                    f"is required: {cleanup_error}"
                )
                failure.recovery_required = True  # type: ignore[attr-defined]
                raise failure from primary
            raise
    raise FoundryPublicationError("cannot allocate governed staging directory")


def write_model_relative(parent_fd: int, name: str, model: BaseModel) -> None:
    """Write a new/replaceable model beneath a pinned directory tree."""
    resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    try:
        _atomic_write_model_relative(
            resolved_parent_fd, basename, model, prefix=f".{Path(name).stem}-"
        )
    finally:
        os.close(resolved_parent_fd)


def write_once_model_relative(
    parent_fd: int, name: str, model: BaseModel
) -> tuple[bool, tuple[int, int]]:
    """Publish one immutable model without replacing an existing leaf."""
    relative = PurePath(name)
    parent_name = str(relative.parent)
    if parent_name != ".":
        directory_fd = ensure_directory_relative(parent_fd, parent_name)
        os.close(directory_fd)
    resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    temporary_name = f".{basename}-{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=resolved_parent_fd,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(model.model_dump_json(indent=2).encode("utf-8"))
            handle.flush()
            identity_metadata = os.fstat(handle.fileno())
            identity = (identity_metadata.st_dev, identity_metadata.st_ino)
            os.fsync(handle.fileno())
        try:
            os.link(
                temporary_name,
                basename,
                src_dir_fd=resolved_parent_fd,
                dst_dir_fd=resolved_parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            content = read_head_relative(resolved_parent_fd, basename)
            if content is None:
                raise FoundryPublicationError(
                    f"governed immutable output disappeared: {name}"
                )
            try:
                existing = type(model).model_validate_json(content)
            except ValueError as exc:
                raise FoundryInputError(
                    f"governed immutable output is invalid: {name}"
                ) from exc
            if existing != model:
                raise FoundryInputError(
                    f"governed immutable output already exists: {name}"
                )
            existing_identity = entry_identity_relative(resolved_parent_fd, basename)
            if existing_identity is None:
                raise FoundryPublicationError(
                    f"governed immutable output disappeared: {name}"
                )
            return True, existing_identity
        if entry_identity_relative(resolved_parent_fd, basename) != identity:
            raise FoundryPublicationError(
                f"governed immutable output identity changed: {name}"
            )
        os.fsync(resolved_parent_fd)
        return False, identity
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=resolved_parent_fd)
        except OSError:
            pass
        os.close(resolved_parent_fd)


def copy_tree_to_directory(source: Path, destination_fd: int, name: str) -> None:
    """Copy a regular-file tree into a new pinned destination directory."""
    if source.is_symlink() or not source.is_dir():
        raise FoundryInputError("candidate artifact tree is unsafe")
    os.mkdir(name, 0o700, dir_fd=destination_fd)
    target_fd = _open_directory(name, parent_fd=destination_fd)
    try:
        _copy_tree_contents(source, target_fd)
        os.fsync(target_fd)
    except BaseException:
        try:
            remove_entry_relative(destination_fd, name)
        except BaseException:
            pass
        raise
    finally:
        os.close(target_fd)


def _copy_tree_contents(source: Path, destination_fd: int) -> None:
    for child in sorted(source.iterdir(), key=lambda item: item.name):
        if child.is_symlink():
            raise FoundryInputError(
                f"candidate artifact is unsafe: {child.relative_to(source)}"
            )
        if child.is_dir():
            os.mkdir(child.name, 0o700, dir_fd=destination_fd)
            child_fd = _open_directory(child.name, parent_fd=destination_fd)
            try:
                _copy_tree_contents(child, child_fd)
                os.fsync(child_fd)
            finally:
                os.close(child_fd)
            continue
        if not child.is_file():
            raise FoundryInputError("candidate artifact contains a non-file")
        target_fd = os.open(
            child.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=destination_fd,
        )
        try:
            with child.open("rb") as source_stream, os.fdopen(
                target_fd, "wb"
            ) as target_stream:
                target_fd = -1
                shutil.copyfileobj(source_stream, target_stream)
                target_stream.flush()
                os.fsync(target_stream.fileno())
        finally:
            if target_fd >= 0:
                os.close(target_fd)


def read_head_relative(parent_fd: int, name: str) -> bytes | None:
    """Capture one regular governance head relative to a pinned directory."""
    try:
        resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise FoundryInputError(f"unsafe governance path: {name}") from exc
    try:
        try:
            metadata = os.stat(
                basename, dir_fd=resolved_parent_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise FoundryInputError(f"governance head path is unsafe: {name}")
        descriptor = os.open(
            basename,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=resolved_parent_fd,
        )
        try:
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read()
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    finally:
        os.close(resolved_parent_fd)


def restore_head_relative(parent_fd: int, name: str, content: bytes | None) -> None:
    """Restore one captured head inside the transaction's pinned namespace."""
    if content is None:
        try:
            resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
        except FileNotFoundError:
            return
        try:
            try:
                os.unlink(basename, dir_fd=resolved_parent_fd)
            except FileNotFoundError:
                return
            os.fsync(resolved_parent_fd)
        finally:
            os.close(resolved_parent_fd)
        return
    _atomic_write_bytes_relative(
        parent_fd, name, content, prefix=f".{Path(name).stem}-rollback-"
    )


def remove_entry_relative(parent_fd: int, name: str) -> None:
    """Remove one transaction-owned entry without resolving a parent pathname."""
    try:
        resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    except FileNotFoundError:
        return
    try:
        try:
            metadata = os.stat(
                basename, dir_fd=resolved_parent_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            return
        if stat.S_ISDIR(metadata.st_mode):
            if not shutil.rmtree.avoids_symlink_attacks:
                raise FoundryPublicationError("safe recursive cleanup is unavailable")
            shutil.rmtree(basename, dir_fd=resolved_parent_fd)
        else:
            os.unlink(basename, dir_fd=resolved_parent_fd)
        os.fsync(resolved_parent_fd)
    finally:
        os.close(resolved_parent_fd)


def entry_identity_relative(parent_fd: int, name: str) -> tuple[int, int] | None:
    try:
        resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    except FileNotFoundError:
        return None
    try:
        try:
            metadata = os.stat(
                basename, dir_fd=resolved_parent_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            return None
        return metadata.st_dev, metadata.st_ino
    finally:
        os.close(resolved_parent_fd)


def remove_owned_entry_relative(
    parent_fd: int, name: str, identity: tuple[int, int]
) -> None:
    current_identity = entry_identity_relative(parent_fd, name)
    if current_identity is None:
        return
    if current_identity != identity:
        raise FoundryPublicationError(
            f"transaction-owned entry identity changed: {name}"
        )
    remove_entry_relative(parent_fd, name)


def directory_fd_path(descriptor: int) -> Path:
    """Resolve a pinned directory descriptor for libraries requiring a pathname."""
    if sys.platform == "darwin":
        # Python's fcntl wrapper caps mutable buffers at 1 KiB, which is also
        # Darwin's path buffer size for F_GETPATH.
        buffer = fcntl.fcntl(descriptor, 50, b"\0" * 1024)  # F_GETPATH
        raw = buffer.split(b"\0", 1)[0]
        if not raw:
            raise FoundryPublicationError("cannot resolve pinned directory")
        return Path(os.fsdecode(raw))
    path = Path("/proc/self/fd") / str(descriptor)
    if path.exists():
        return path
    raise FoundryPublicationError("cannot resolve pinned directory")


def validate_governance_namespace(
    project_root: Path,
    docset_id: str,
    *,
    api_fd: int,
    docset_fd: int,
    assets_fd: int,
) -> None:
    """Fail if canonical pathnames no longer name the pinned transaction tree."""
    expected = (
        (api_fd, project_root / paths.FOUNDRY_DIR / paths.API_DIR),
        (docset_fd, paths.docset_dir(project_root, docset_id)),
        (assets_fd, paths.assets_dir(project_root, docset_id)),
    )
    try:
        if any(
            not os.path.samestat(os.fstat(descriptor), path.stat())
            for descriptor, path in expected
        ):
            raise FoundryPublicationError(
                "governance namespace changed during transaction"
            )
    except FoundryPublicationError:
        raise
    except OSError as exc:
        raise FoundryPublicationError(
            "governance namespace changed during transaction"
        ) from exc


def validate_catalog_namespace(
    project_root: Path,
    *,
    root_fd: int,
    foundry_fd: int,
    api_fd: int,
    docsets_fd: int,
) -> None:
    """Fail if canonical catalog pathnames no longer name the pinned tree."""
    expected = (
        (root_fd, project_root),
        (foundry_fd, project_root / paths.FOUNDRY_DIR),
        (api_fd, project_root / paths.FOUNDRY_DIR / paths.API_DIR),
        (docsets_fd, paths.docsets_root(project_root)),
    )
    try:
        if any(path.is_symlink() for _, path in expected) or any(
            not os.path.samestat(os.fstat(descriptor), path.stat())
            for descriptor, path in expected
        ):
            raise FoundryPublicationError(
                "catalog governance namespace changed during transaction"
            )
    except FoundryPublicationError:
        raise
    except OSError as exc:
        raise FoundryPublicationError(
            "catalog governance namespace changed during transaction"
        ) from exc


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
    project_root: Path, catalog: Catalog, *, parent_fd: int | None = None
) -> None:
    if parent_fd is None:
        _write_model(paths.catalog_path(project_root), catalog)
    else:
        _atomic_write_model_relative(parent_fd, "catalog.json", catalog, prefix=".catalog-")


def load_docset(project_root: Path, docset_id: str) -> Docset:
    return _read_model(
        Docset, paths.docset_manifest_path(project_root, docset_id), "docset.json"
    )


def save_docset(
    project_root: Path, docset: Docset, *, parent_fd: int | None = None
) -> None:
    if parent_fd is None:
        _write_model(paths.docset_manifest_path(project_root, docset.docset_id), docset)
    else:
        _atomic_write_model_relative(parent_fd, "docset.json", docset, prefix=".docset-")


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
        # The root has already been renamed.  Surface inability to verify or
        # fsync the parent so the approval transaction can restore heads and
        # remove this exact newly published root before a retry.
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
) -> None:
    """Atomically publish the normative current pointer."""
    if parent_fd is None:
        _atomic_write_model(
            paths.current_path(project_root, docset_id), pointer, prefix=".current-"
        )
    else:
        _atomic_write_model_relative(parent_fd, "current.json", pointer, prefix=".current-")


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
    *,
    parent_fd: int | None = None,
    scope_parent_fd: int | None = None,
) -> None:
    """Atomically publish the externally consumed scope-specific pointer."""
    if scope_parent_fd is not None:
        _atomic_write_model_relative(
            scope_parent_fd, "current.json", pointer, prefix=".current-"
        )
    elif parent_fd is None:
        _atomic_write_model(
            paths.effective_current_path(project_root, docset_id, scope_digest),
            pointer,
            prefix=".current-",
        )
    else:
        _atomic_write_model_relative(
            parent_fd,
            f"effective/scopes/{scope_digest}/current.json",
            pointer,
            prefix=".current-",
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
