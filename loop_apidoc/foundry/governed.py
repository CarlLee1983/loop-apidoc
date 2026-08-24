"""Pinned descriptor views and namespace validation for Foundry docsets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from . import descriptor_io, descriptor_namespace, paths
from .models import FoundryInputError, FoundryPublicationError

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
                raise FoundryInputError(
                    f"governance ancestor escapes project root: {ancestor}"
                )


def _open_governance_directories(
    project_root: Path, docset_id: str, *, create_assets: bool = True
) -> tuple[int, int, int, int]:
    """Open the governed path one component at a time, refusing symlinks."""
    root_fd = descriptor_namespace._open_directory(project_root)
    opened = [root_fd]
    try:
        foundry_fd = descriptor_namespace._open_directory(
            paths.FOUNDRY_DIR, parent_fd=root_fd
        )
        opened.append(foundry_fd)
        api_fd = descriptor_namespace._open_directory(
            paths.API_DIR, parent_fd=foundry_fd
        )
        opened.append(api_fd)
        docsets_fd = descriptor_namespace._open_directory("docsets", parent_fd=api_fd)
        opened.append(docsets_fd)
        docset_fd = descriptor_namespace._open_directory(
            docset_id, parent_fd=docsets_fd
        )
        opened.append(docset_fd)
        assets_fd = -1
        try:
            assets_fd = descriptor_namespace._open_directory(
                "assets", parent_fd=docset_fd
            )
        except FileNotFoundError:
            if create_assets:
                os.mkdir("assets", dir_fd=docset_fd)
                assets_fd = descriptor_namespace._open_directory(
                    "assets", parent_fd=docset_fd
                )
        if assets_fd >= 0:
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
class GovernedDocset:
    """Pinned descriptor view of one governed docset.

    Callers consume governed feedback and Effective state through this view rather
    than resolving paths beneath ``.foundry``. Each nested directory is opened
    with ``O_NOFOLLOW`` and can be revalidated before a write is committed.
    """

    project_root: Path
    docset_id: str
    root_fd: int
    foundry_fd: int
    api_fd: int
    docsets_fd: int
    docset_fd: int
    _closed: bool = False

    def __enter__(self) -> GovernedDocset:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        for descriptor in (
            self.docset_fd,
            self.docsets_fd,
            self.api_fd,
            self.foundry_fd,
            self.root_fd,
        ):
            try:
                os.close(descriptor)
            except OSError:
                pass
        self._closed = True

    def read_bytes(
        self,
        relative: str,
        label: str,
        *,
        optional: bool = False,
        max_bytes: int | None = None,
    ) -> bytes | None:
        return descriptor_io.read_bytes_relative(
            self.docset_fd,
            relative,
            label,
            optional=optional,
            max_bytes=max_bytes,
        )

    def read_model(
        self,
        model: type[_ModelT],
        relative: str,
        label: str,
        *,
        optional: bool = False,
        max_bytes: int | None = None,
    ) -> _ModelT | None:
        return descriptor_io.read_model_relative(
            self.docset_fd,
            model,
            relative,
            label,
            optional=optional,
            max_bytes=max_bytes,
        )

    def read_api_model(
        self,
        model: type[_ModelT],
        relative: str,
        label: str,
        *,
        optional: bool = False,
        max_bytes: int | None = None,
    ) -> _ModelT | None:
        """Read an API-level model through the held Foundry descriptor."""
        return descriptor_io.read_model_relative(
            self.api_fd,
            model,
            relative,
            label,
            optional=optional,
            max_bytes=max_bytes,
        )

    def open_directory(self, relative: str) -> GovernedDirectory:
        try:
            descriptor = descriptor_namespace.open_directory_relative(
                self.docset_fd, relative
            )
        except (FoundryInputError, OSError) as exc:
            raise FoundryInputError(f"unsafe governed directory: {relative}") from exc
        return GovernedDirectory(self, relative, descriptor)

    def validate(self) -> None:
        descriptor_namespace.validate_pinned_directory_chain(
            self.project_root,
            expected_root_fd=self.root_fd,
            components=(
                (paths.FOUNDRY_DIR, self.foundry_fd),
                (paths.API_DIR, self.api_fd),
                ("docsets", self.docsets_fd),
                (self.docset_id, self.docset_fd),
            ),
            message="governed docset namespace changed during operation",
        )


@dataclass
class GovernedDirectory:
    """A pinned nested directory beneath a :class:`GovernedDocset`."""

    docset: GovernedDocset
    relative: str
    descriptor: int
    _closed: bool = False

    def __enter__(self) -> GovernedDirectory:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        os.close(self.descriptor)
        self._closed = True

    def read_bytes(
        self,
        relative: str,
        label: str,
        *,
        optional: bool = False,
        max_bytes: int | None = None,
    ) -> bytes | None:
        return descriptor_io.read_bytes_relative(
            self.descriptor,
            relative,
            label,
            optional=optional,
            max_bytes=max_bytes,
        )

    def read_model(
        self,
        model: type[_ModelT],
        relative: str,
        label: str,
        *,
        optional: bool = False,
        max_bytes: int | None = None,
    ) -> _ModelT | None:
        return descriptor_io.read_model_relative(
            self.descriptor,
            model,
            relative,
            label,
            optional=optional,
            max_bytes=max_bytes,
        )

    def ensure_directory(self, relative: str) -> GovernedDirectory:
        try:
            descriptor = descriptor_namespace.ensure_directory_relative(
                self.descriptor, relative
            )
        except (FoundryInputError, OSError) as exc:
            raise FoundryInputError(f"unsafe governed directory: {relative}") from exc
        return GovernedDirectory(
            self.docset, f"{self.relative}/{relative}", descriptor
        )

    def open_directory(self, relative: str) -> GovernedDirectory:
        """Open a nested directory from this pinned parent descriptor."""
        try:
            descriptor = descriptor_namespace.open_directory_relative(
                self.descriptor, relative
            )
        except (FoundryInputError, OSError) as exc:
            raise FoundryInputError(f"unsafe governed directory: {relative}") from exc
        return GovernedDirectory(
            self.docset, f"{self.relative}/{relative}", descriptor
        )

    def digest_artifact(self, relative: str, kind: str, label: str = "artifact") -> str:
        """Digest a bound artifact without reopening a governed pathname."""
        return descriptor_io.digest_artifact_relative(
            self.descriptor, relative, kind, label
        )

    def validate(self) -> None:
        descriptor_namespace.validate_directory_relative(
            self.docset.docset_fd, self.relative, self.descriptor
        )

    def write_once_model(
        self, relative: str, model: BaseModel
    ) -> tuple[bool, tuple[int, int]]:
        self.validate()
        publication = descriptor_io.ImmutableEntryPublication()
        try:
            existed, identity = descriptor_io.write_once_model_relative(
                self.descriptor, relative, model, outcome=publication
            )
            self.validate()
            self.docset.validate()
        except BaseException:
            if publication.owned_entry:
                if publication.identity is None:
                    raise FoundryPublicationError(
                        "immutable governed output ownership is unavailable"
                    )
                descriptor_namespace.remove_owned_entry_relative(
                    self.descriptor, relative, publication.identity
                )
            raise
        return existed, identity


def open_governed_docset(project_root: Path, docset_id: str) -> GovernedDocset:
    """Open a docset from pinned descriptors without following governed links."""
    if (
        not docset_id
        or docset_id in {".", ".."}
        or "/" in docset_id
        or "\\" in docset_id
    ):
        raise FoundryInputError("unsafe docset id")
    project_root = _normalise_project_root(project_root)
    descriptors: list[int] = []
    try:
        root_fd = descriptor_namespace._open_directory(project_root)
        descriptors.append(root_fd)
        foundry_fd = descriptor_namespace._open_directory(
            paths.FOUNDRY_DIR, parent_fd=root_fd
        )
        descriptors.append(foundry_fd)
        api_fd = descriptor_namespace._open_directory(
            paths.API_DIR, parent_fd=foundry_fd
        )
        descriptors.append(api_fd)
        docsets_fd = descriptor_namespace._open_directory("docsets", parent_fd=api_fd)
        descriptors.append(docsets_fd)
        docset_fd = descriptor_namespace._open_directory(
            docset_id, parent_fd=docsets_fd
        )
        descriptors.append(docset_fd)
    except OSError as exc:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise FoundryInputError("cannot open governed docset safely") from exc
    return GovernedDocset(
        project_root=project_root,
        docset_id=docset_id,
        root_fd=root_fd,
        foundry_fd=foundry_fd,
        api_fd=api_fd,
        docsets_fd=docsets_fd,
        docset_fd=docset_fd,
    )


def open_pinned_governed_docset(
    project_root: Path,
    docset_id: str,
    *,
    root_fd: int,
    api_fd: int,
    docset_fd: int,
) -> GovernedDocset:
    """Build a query view only from a transaction's already-held descriptors."""
    if (
        not docset_id
        or docset_id in {".", ".."}
        or "/" in docset_id
        or "\\" in docset_id
    ):
        raise FoundryInputError("unsafe docset id")
    descriptors: list[int] = []
    try:
        duplicated_root_fd = os.dup(root_fd)
        descriptors.append(duplicated_root_fd)
        foundry_fd = descriptor_namespace._open_directory(
            paths.FOUNDRY_DIR, parent_fd=duplicated_root_fd
        )
        descriptors.append(foundry_fd)
        duplicated_api_fd = descriptor_namespace._open_directory(
            paths.API_DIR, parent_fd=foundry_fd
        )
        descriptors.append(duplicated_api_fd)
        docsets_fd = descriptor_namespace._open_directory(
            "docsets", parent_fd=duplicated_api_fd
        )
        descriptors.append(docsets_fd)
        duplicated_docset_fd = descriptor_namespace._open_directory(
            docset_id, parent_fd=docsets_fd
        )
        descriptors.append(duplicated_docset_fd)
        if not os.path.samestat(os.fstat(duplicated_api_fd), os.fstat(api_fd)):
            raise FoundryPublicationError(
                "governed transaction namespace changed during operation"
            )
        if not os.path.samestat(os.fstat(duplicated_docset_fd), os.fstat(docset_fd)):
            raise FoundryPublicationError(
                "governed transaction namespace changed during operation"
            )
    except BaseException:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    return GovernedDocset(
        project_root=project_root,
        docset_id=docset_id,
        root_fd=duplicated_root_fd,
        foundry_fd=foundry_fd,
        api_fd=duplicated_api_fd,
        docsets_fd=docsets_fd,
        docset_fd=duplicated_docset_fd,
    )


def validate_governance_namespace(
    project_root: Path,
    docset_id: str,
    *,
    api_fd: int,
    docset_fd: int,
    assets_fd: int,
    root_fd: int | None = None,
) -> None:
    """Fail if canonical pathnames no longer name the pinned transaction tree."""
    components: tuple[tuple[str, int | None], ...] = (
        (paths.FOUNDRY_DIR, None),
        (paths.API_DIR, api_fd),
        ("docsets", None),
        (docset_id, docset_fd),
    )
    if assets_fd >= 0:
        components += (("assets", assets_fd),)
    descriptor_namespace.validate_pinned_directory_chain(
        project_root,
        expected_root_fd=root_fd,
        components=components,
        message="governance namespace changed during transaction",
    )


def validate_catalog_namespace(
    project_root: Path,
    *,
    root_fd: int,
    foundry_fd: int,
    api_fd: int,
    docsets_fd: int,
) -> None:
    """Fail if canonical catalog pathnames no longer name the pinned tree."""
    descriptor_namespace.validate_pinned_directory_chain(
        project_root,
        expected_root_fd=root_fd,
        components=(
            (paths.FOUNDRY_DIR, foundry_fd),
            (paths.API_DIR, api_fd),
            ("docsets", docsets_fd),
        ),
        message="catalog governance namespace changed during transaction",
    )
