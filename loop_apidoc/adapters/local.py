from __future__ import annotations

import hashlib
import os
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.atomic_publish import (
    DirectoryPublicationCollisionError,
    publish_directory_noreplace,
)
from loop_apidoc.core.artifacts import projection_content_address
from loop_apidoc.core.models import (
    ContractRelease,
    EvidenceBundle,
    EvidenceFragment,
    ReleaseStatus,
    SourceArtifact,
    SourceSet,
)
from loop_apidoc.domain.projections import Projection


class LocalFileSourceAdapter:
    def acquire(self, source_set: SourceSet) -> EvidenceBundle:
        artifacts: list[SourceArtifact] = []
        fragments: list[EvidenceFragment] = []
        now = datetime.now(timezone.utc)
        for source in source_set.sources:
            if source.kind != "file":
                raise ValueError(f"unsupported local source kind: {source.kind}")
            path = Path(source.locator)
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            artifact_id = f"artifact-{digest[:24]}"
            artifacts.append(
                SourceArtifact(
                    id=artifact_id,
                    source_id=source.id,
                    media_type=source.media_type or "application/octet-stream",
                    content_digest=digest,
                    acquired_at=now,
                    acquisition_metadata=(("filename", path.name),),
                )
            )
            fragments.append(
                EvidenceFragment(
                    id=f"fragment-{digest[:24]}",
                    source_artifact_id=artifact_id,
                    locator="whole",
                    fragment_digest=digest,
                )
            )
        return EvidenceBundle(
            source_set_id=source_set.id,
            source_set_version=source_set.version,
            artifacts=tuple(artifacts),
            fragments=tuple(fragments),
        )


class DirectoryArtifactSink:
    """Publish content-addressed projection trees inside one controlled root.

    The root is a sink-owned namespace: returned paths remain trustworthy only
    while no out-of-band writer mutates it.  They are durable locators, not
    immutable file capabilities.  Each reuse verifies a complete regular-file
    tree twice through pinned descriptors and refuses aliases such as links.

    Failed or raced publications deliberately retain their hidden staging tree.
    Portable POSIX cannot recursively remove a pathname while proving it still
    names the entry we created, so automatic cleanup could delete a substitute.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def publish(
        self,
        release: ContractRelease,
        projections: tuple[Projection, ...],
    ) -> tuple[str, ...]:
        if release.status is not ReleaseStatus.APPROVED:
            raise ValueError("only approved releases may publish artifacts")
        if not projections:
            raise ValueError("artifact publication requires at least one projection")
        publication_id = projection_content_address(projections)
        self.root.mkdir(parents=True, exist_ok=True)
        root_fd = _open_directory_path(self.root, "artifact root")
        try:
            if _entry_metadata(root_fd, publication_id) is not None:
                refs = self._existing_refs(root_fd, publication_id, projections)
                _assert_root_binding(self.root, root_fd)
                return refs
            staging_name, staging_fd = _create_staging_directory(root_fd, publication_id)
            for projection in projections:
                _write_projection_relative(staging_fd, projection)
            try:
                staging_identity = _identity(os.fstat(staging_fd))
                if _entry_identity(root_fd, staging_name) != staging_identity:
                    raise ValueError("artifact staging identity changed before publication")
                publish_directory_noreplace(
                    Path(staging_name),
                    Path(publication_id),
                    parent_fd=root_fd,
                )
            except DirectoryPublicationCollisionError:
                refs = self._existing_refs(root_fd, publication_id, projections)
            else:
                if _entry_identity(root_fd, publication_id) != staging_identity:
                    raise ValueError("published artifact identity changed during publication")
                refs = self._existing_refs(root_fd, publication_id, projections)
            _assert_root_binding(self.root, root_fd)
            return refs
        finally:
            if "staging_fd" in locals():
                os.close(staging_fd)
            os.close(root_fd)

    def _existing_refs(
        self,
        root_fd: int,
        publication_id: str,
        projections: tuple[Projection, ...],
    ) -> tuple[str, ...]:
        destination_fd = _open_directory_relative(
            root_fd, publication_id, "published artifact address"
        )
        destination_identity = _identity(os.fstat(destination_fd))
        try:
            actual_files, actual_directories = _read_artifact_tree(destination_fd)
            confirmed_files, confirmed_directories = _read_artifact_tree(
                destination_fd
            )
            if (
                actual_files != confirmed_files
                or actual_directories != confirmed_directories
                or _identity(os.fstat(destination_fd)) != destination_identity
            ):
                raise ValueError("published artifact identity changed during read")
        finally:
            os.close(destination_fd)
        expected_files = {_safe_projection_name(projection) for projection in projections}
        expected_directories = _projection_directories(expected_files)
        if set(actual_files) != expected_files or actual_directories != expected_directories:
            raise ValueError("published artifact content does not match its address")
        refs: list[str] = []
        for projection in projections:
            name = _safe_projection_name(projection)
            if actual_files[name][1] != projection.content:
                raise ValueError("published artifact content does not match its address")
            refs.append(str(self.root / publication_id / name))
        if _entry_identity(root_fd, publication_id) != destination_identity:
            raise ValueError("published artifact identity changed during read")
        return tuple(refs)


def _no_follow_directory_flags() -> int:
    directory = getattr(os, "O_DIRECTORY", None)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if directory is None or no_follow is None:
        raise ValueError("secure artifact publication is unavailable on this platform")
    return os.O_RDONLY | directory | no_follow | getattr(os, "O_CLOEXEC", 0)


def _open_directory_path(path: Path, label: str) -> int:
    try:
        return os.open(path, _no_follow_directory_flags())
    except OSError as exc:
        raise ValueError(f"{label} must be a real non-symlink directory") from exc


def _entry_metadata(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _entry_identity(parent_fd: int, name: str) -> tuple[int, int] | None:
    metadata = _entry_metadata(parent_fd, name)
    return None if metadata is None else _identity(metadata)


def _open_directory_relative(parent_fd: int, name: str, label: str) -> int:
    metadata = _entry_metadata(parent_fd, name)
    if metadata is None:
        raise ValueError(f"{label} is missing")
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"{label} is a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{label} is not a directory")
    try:
        descriptor = os.open(
            name,
            _no_follow_directory_flags(),
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise ValueError(f"{label} is not a real directory") from exc
    if _identity(os.fstat(descriptor)) != _identity(metadata):
        os.close(descriptor)
        raise ValueError(f"{label} identity changed during open")
    return descriptor


def _create_staging_directory(parent_fd: int, publication_id: str) -> tuple[str, int]:
    for _ in range(64):
        name = f".{publication_id}-{uuid.uuid4().hex}"
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        return name, _open_directory_relative(parent_fd, name, "artifact staging")
    raise ValueError("could not allocate a unique artifact staging directory")


def _write_projection_relative(staging_fd: int, projection: Projection) -> None:
    components = Path(_safe_projection_name(projection)).parts
    directory_fd = os.dup(staging_fd)
    try:
        for component in components[:-1]:
            try:
                os.mkdir(component, mode=0o700, dir_fd=directory_fd)
            except FileExistsError:
                pass
            next_fd = _open_directory_relative(
                directory_fd, component, "artifact projection directory"
            )
            os.close(directory_fd)
            directory_fd = next_fd
        try:
            file_fd = os.open(
                components[-1],
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=directory_fd,
            )
        except OSError as exc:
            raise ValueError("artifact projection path is not writable") from exc
        try:
            view = memoryview(projection.content)
            while view:
                written = os.write(file_fd, view)
                view = view[written:]
        finally:
            os.close(file_fd)
    finally:
        os.close(directory_fd)


ArtifactFile = tuple[tuple[int, int], bytes]


def _read_artifact_tree(
    directory_fd: int, prefix: tuple[str, ...] = ()
) -> tuple[dict[str, ArtifactFile], set[str]]:
    files: dict[str, ArtifactFile] = {}
    directories: set[str] = set()
    for name in os.listdir(directory_fd):
        path = prefix + (name,)
        relative = "/".join(path)
        metadata = _entry_metadata(directory_fd, name)
        if metadata is None:
            raise ValueError("published artifact identity changed during read")
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("published artifact content contains a symlink")
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = _open_directory_relative(
                directory_fd, name, "published artifact directory"
            )
            try:
                child_files, child_directories = _read_artifact_tree(child_fd, path)
            finally:
                os.close(child_fd)
            directories.add(relative)
            files.update(child_files)
            directories.update(child_directories)
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("published artifact content has an unsafe entry")
        if metadata.st_nlink != 1:
            raise ValueError("published artifact content contains a hard link")
        try:
            file_fd = os.open(
                name,
                os.O_RDONLY
                | os.O_NONBLOCK
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_fd,
            )
        except OSError as exc:
            raise ValueError("published artifact content has an unsafe entry") from exc
        try:
            opened = os.fstat(file_fd)
            if _identity(opened) != _identity(metadata) or not stat.S_ISREG(opened.st_mode):
                raise ValueError("published artifact identity changed during read")
            if opened.st_nlink != 1:
                raise ValueError("published artifact content contains a hard link")
            content = b"".join(iter(lambda: os.read(file_fd, 65536), b""))
        finally:
            os.close(file_fd)
        files[relative] = _identity(opened), content
    return files, directories


def _projection_directories(names: set[str]) -> set[str]:
    directories: set[str] = set()
    for name in names:
        parts = Path(name).parts[:-1]
        for index in range(1, len(parts) + 1):
            directories.add("/".join(parts[:index]))
    return directories


def _assert_root_binding(root: Path, root_fd: int) -> None:
    current_fd = _open_directory_path(root, "artifact root")
    try:
        if not os.path.samestat(os.fstat(current_fd), os.fstat(root_fd)):
            raise ValueError("artifact root identity changed during publication")
    finally:
        os.close(current_fd)


def _safe_projection_name(projection: Projection) -> str:
    name = Path(projection.name)
    if name.is_absolute() or ".." in name.parts or not name.parts:
        raise ValueError("projection name must be a relative artifact path")
    return name.as_posix()
