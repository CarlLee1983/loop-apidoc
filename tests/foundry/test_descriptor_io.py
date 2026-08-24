"""Public descriptor-I/O seams retain their namespace and content bindings."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from loop_apidoc.foundry import descriptor_io
from loop_apidoc.foundry.models import (
    Docset,
    FoundryInputError,
    FoundryPublicationError,
)


def _docset(*, title: str = "TapPay Backend API") -> Docset:
    return Docset(
        docset_id="tappay-backend",
        title=title,
        provider="tappay",
        product="backend-api",
    )


def _open_root(path: Path) -> int:
    return os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_write_once_model_creates_nested_owned_directories_and_reads_back(
    tmp_path: Path,
) -> None:
    root_fd = _open_root(tmp_path)
    original = _docset()
    try:
        _existed, identity = descriptor_io.write_once_model_relative(
            root_fd, "docsets/tappay/models/docset.json", original
        )

        assert (tmp_path / "docsets" / "tappay" / "models").is_dir()
        assert descriptor_io.entry_identity_relative(
            root_fd, "docsets/tappay/models/docset.json"
        ) == identity
        assert (
            descriptor_io.read_model_relative(
                root_fd,
                Docset,
                "docsets/tappay/models/docset.json",
                "docset.json",
            )
            == original
        )
    finally:
        os.close(root_fd)


def test_write_once_model_preserves_the_first_immutable_document(tmp_path: Path) -> None:
    root_fd = _open_root(tmp_path)
    original = _docset()
    try:
        descriptor_io.write_once_model_relative(root_fd, "docset.json", original)

        with pytest.raises(FoundryInputError, match="immutable output already exists"):
            descriptor_io.write_once_model_relative(
                root_fd, "docset.json", _docset(title="Changed after publication")
            )

        assert (
            descriptor_io.read_model_relative(
                root_fd, Docset, "docset.json", "docset.json"
            )
            == original
        )
    finally:
        os.close(root_fd)


def test_read_model_rejects_malformed_and_oversize_documents(tmp_path: Path) -> None:
    root_fd = _open_root(tmp_path)
    try:
        (tmp_path / "invalid.json").write_text("{not json", encoding="utf-8")
        (tmp_path / "large.json").write_bytes(b"x" * 64)

        with pytest.raises(FoundryInputError, match="invalid.json is invalid"):
            descriptor_io.read_model_relative(
                root_fd, Docset, "invalid.json", "invalid.json"
            )
        with pytest.raises(FoundryInputError, match="large.json exceeds size limit"):
            descriptor_io.read_model_relative(
                root_fd, Docset, "large.json", "large.json", max_bytes=32
            )
    finally:
        os.close(root_fd)


def test_digest_artifact_relative_binds_file_bytes_and_sorted_tree_entries(
    tmp_path: Path,
) -> None:
    root_fd = _open_root(tmp_path)
    try:
        (tmp_path / "openapi.yaml").write_bytes(b"openapi: 3.1.0\n")
        tree = tmp_path / "handoff"
        (tree / "nested").mkdir(parents=True)
        (tree / "b.md").write_bytes(b"second")
        (tree / "a.md").write_bytes(b"first")
        (tree / "nested" / "c.md").write_bytes(b"third")

        expected_tree = hashlib.sha256(
            json.dumps(
                [
                    ("a.md", _sha256(b"first")),
                    ("b.md", _sha256(b"second")),
                    ("nested/c.md", _sha256(b"third")),
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        assert descriptor_io.digest_artifact_relative(
            root_fd, "openapi.yaml", "file", "OpenAPI"
        ) == _sha256(b"openapi: 3.1.0\n")
        assert descriptor_io.digest_artifact_relative(
            root_fd, "handoff", "tree", "handoff"
        ) == expected_tree
    finally:
        os.close(root_fd)


def test_descriptor_io_rejects_traversal_and_symlinked_paths(tmp_path: Path) -> None:
    root_fd = _open_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.json").write_text("{}", encoding="utf-8")
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(FoundryInputError, match="unsafe governance relative path"):
            descriptor_io.read_bytes_relative(root_fd, "../outside/secret.json", "secret")
        with pytest.raises(FoundryInputError, match="secret path is unsafe"):
            descriptor_io.read_bytes_relative(root_fd, "linked/secret.json", "secret")
        with pytest.raises(FoundryInputError, match="unsafe governance path"):
            descriptor_io.ensure_directory_relative(root_fd, "linked/new-child")
    finally:
        os.close(root_fd)


def test_tree_digest_rejects_a_symlinked_artifact_entry(tmp_path: Path) -> None:
    root_fd = _open_root(tmp_path)
    tree = tmp_path / "handoff"
    tree.mkdir()
    (tmp_path / "outside.md").write_text("not governed", encoding="utf-8")
    (tree / "leaked.md").symlink_to(tmp_path / "outside.md")
    try:
        with pytest.raises(FoundryInputError, match="unsafe artifact path: handoff"):
            descriptor_io.digest_artifact_relative(
                root_fd, "handoff", "tree", "handoff"
            )
    finally:
        os.close(root_fd)


def test_read_bytes_allows_an_optional_absent_file_but_rejects_unsafe_entries(
    tmp_path: Path,
) -> None:
    root_fd = _open_root(tmp_path)
    (tmp_path / "directory").mkdir()
    (tmp_path / "payload.json").write_bytes(b"payload")
    (tmp_path / "link.json").symlink_to(tmp_path / "payload.json")
    (tmp_path / "large.json").write_bytes(b"x" * 64)
    try:
        assert (
            descriptor_io.read_bytes_relative(
                root_fd, "missing.json", "optional document", optional=True
            )
            is None
        )
        with pytest.raises(FoundryInputError, match="directory path is unsafe"):
            descriptor_io.read_bytes_relative(root_fd, "directory", "directory")
        with pytest.raises(FoundryInputError, match="link path is unsafe"):
            descriptor_io.read_bytes_relative(root_fd, "link.json", "link")
        with pytest.raises(FoundryInputError, match="large exceeds size limit"):
            descriptor_io.read_bytes_relative(
                root_fd, "large.json", "large", max_bytes=32
            )
    finally:
        os.close(root_fd)


def test_copy_tree_to_owned_directory_copies_nested_regular_files(tmp_path: Path) -> None:
    source = tmp_path / "candidate"
    (source / "nested").mkdir(parents=True)
    (source / "asset.json").write_text("{}", encoding="utf-8")
    (source / "nested" / "artifact.txt").write_text("payload", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    destination_fd = _open_root(destination)
    try:
        name, copied_fd, identity = descriptor_io.copy_tree_to_owned_directory(
            source, destination_fd, prefix=".candidate-"
        )
        try:
            assert descriptor_io.entry_identity_relative(destination_fd, name) == identity
            assert (destination / name / "nested" / "artifact.txt").read_text(
                encoding="utf-8"
            ) == "payload"
        finally:
            os.close(copied_fd)
    finally:
        os.close(destination_fd)


def test_copy_tree_to_directory_rejects_a_non_regular_source_entry(
    tmp_path: Path,
) -> None:
    source = tmp_path / "candidate"
    source.mkdir()
    os.mkfifo(source / "pipe")
    destination = tmp_path / "destination"
    destination.mkdir()
    destination_fd = _open_root(destination)
    try:
        with pytest.raises(FoundryInputError, match="contains a non-file"):
            descriptor_io.copy_tree_to_directory(source, destination_fd, "published")

        assert not (destination / "published").exists()
    finally:
        os.close(destination_fd)


def test_head_snapshot_detects_mutation_and_restore_replaces_head_bytes(
    tmp_path: Path,
) -> None:
    root_fd = _open_root(tmp_path)
    original = _docset()
    updated = _docset(title="Updated title")
    try:
        descriptor_io.write_model_relative(root_fd, "docset.json", original)
        snapshot = descriptor_io.read_head_snapshot_relative(root_fd, "docset.json")
        assert snapshot.content == original.model_dump_json(indent=2).encode("utf-8")

        descriptor_io.write_model_relative(root_fd, "docset.json", updated)
        with pytest.raises(FoundryPublicationError, match="head identity changed"):
            descriptor_io.validate_head_snapshot_relative(
                root_fd, "docset.json", snapshot
            )

        descriptor_io.restore_head_relative(root_fd, "docset.json", snapshot.content)
        assert descriptor_io.read_model_relative(
            root_fd, Docset, "docset.json", "docset.json"
        ) == original
    finally:
        os.close(root_fd)


def test_move_owned_directory_requires_its_identity_and_an_absent_destination(
    tmp_path: Path,
) -> None:
    root_fd = _open_root(tmp_path)
    try:
        source_fd = descriptor_io.ensure_directory_relative(root_fd, "staged")
        try:
            identity = (os.fstat(source_fd).st_dev, os.fstat(source_fd).st_ino)
        finally:
            os.close(source_fd)

        assert descriptor_io.move_owned_directory_relative(
            root_fd, "staged", "published", identity
        ) == identity
        assert (tmp_path / "published").is_dir()

        occupied_fd = descriptor_io.ensure_directory_relative(root_fd, "occupied")
        os.close(occupied_fd)
        with pytest.raises(FoundryInputError, match="destination already exists"):
            descriptor_io.move_owned_directory_relative(
                root_fd, "published", "occupied", identity
            )

        (tmp_path / "published").rename(tmp_path / "retired")
        (tmp_path / "published").mkdir()
        with pytest.raises(FoundryPublicationError, match="identity changed"):
            descriptor_io.move_owned_directory_relative(
                root_fd, "published", "replacement", identity
            )
    finally:
        os.close(root_fd)
