"""Guards on the governed-artifact capture primitives.

`read_verified_file` and `digest_artifact` are the boundary that decides whether a
byte sequence is allowed to represent a governed artifact. Every rejection below is
the reason a caller may trust the value it gets back, so each one is asserted here
rather than left to the callers that happen to exercise the happy path.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from loop_apidoc.foundry.integrity import digest_artifact, read_verified_file
from loop_apidoc.foundry.models import FoundryInputError


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_read_verified_file_returns_the_bytes_matching_the_expected_digest(
    tmp_path: Path,
) -> None:
    target = tmp_path / "asset.json"
    target.write_bytes(b'{"ok": true}')

    assert read_verified_file(target, _digest(b'{"ok": true}')) == b'{"ok": true}'


def test_read_verified_file_rejects_a_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    real.write_bytes(b"{}")
    link = tmp_path / "link.json"
    link.symlink_to(real)

    with pytest.raises(FoundryInputError, match="missing or unsafe: current.json"):
        read_verified_file(link, _digest(b"{}"), "current.json")


def test_read_verified_file_rejects_a_directory(tmp_path: Path) -> None:
    directory = tmp_path / "asset.json"
    directory.mkdir()

    with pytest.raises(FoundryInputError, match="missing or unsafe"):
        read_verified_file(directory, _digest(b""))


def test_read_verified_file_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FoundryInputError, match="missing or unsafe"):
        read_verified_file(tmp_path / "absent.json", _digest(b""))


def test_read_verified_file_stops_at_the_size_limit_without_buffering_the_rest(
    tmp_path: Path,
) -> None:
    target = tmp_path / "big.json"
    target.write_bytes(b"x" * 2048)

    with pytest.raises(FoundryInputError, match="exceeds size limit: bundle"):
        read_verified_file(target, _digest(b"x" * 2048), "bundle", max_bytes=1024)


def test_read_verified_file_reports_an_unreadable_file_as_input_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "asset.json"
    target.write_bytes(b"{}")

    def fail_open(*_args: object, **_kwargs: object) -> None:
        raise OSError("device is gone")

    monkeypatch.setattr(Path, "open", fail_open)
    with pytest.raises(FoundryInputError, match="cannot read artifact: asset.json"):
        read_verified_file(target, _digest(b"{}"), "asset.json")


def test_read_verified_file_rejects_content_that_does_not_match_the_digest(
    tmp_path: Path,
) -> None:
    target = tmp_path / "asset.json"
    target.write_bytes(b"tampered")

    with pytest.raises(FoundryInputError, match="digest is stale: asset.json"):
        read_verified_file(target, _digest(b"original"), "asset.json")


def test_digest_artifact_digests_a_file_as_its_raw_bytes(tmp_path: Path) -> None:
    target = tmp_path / "openapi.yaml"
    target.write_bytes(b"openapi: 3.1.0\n")

    assert digest_artifact(target, "file") == _digest(b"openapi: 3.1.0\n")


def test_digest_artifact_rejects_a_symlinked_file(tmp_path: Path) -> None:
    real = tmp_path / "real.yaml"
    real.write_bytes(b"openapi: 3.1.0\n")
    link = tmp_path / "link.yaml"
    link.symlink_to(real)

    with pytest.raises(FoundryInputError, match="missing or unsafe: openapi"):
        digest_artifact(link, "file", "openapi")


def test_digest_artifact_reports_an_unreadable_file_as_input_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "openapi.yaml"
    target.write_bytes(b"openapi: 3.1.0\n")

    def fail_read(*_args: object, **_kwargs: object) -> bytes:
        raise OSError("device is gone")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(FoundryInputError, match="cannot read artifact: openapi"):
        digest_artifact(target, "file", "openapi")


def test_digest_artifact_rejects_an_unknown_kind(tmp_path: Path) -> None:
    target = tmp_path / "openapi.yaml"
    target.write_bytes(b"openapi: 3.1.0\n")

    with pytest.raises(FoundryInputError, match="unknown artifact kind: openapi"):
        digest_artifact(target, "blob", "openapi")


def test_digest_artifact_rejects_a_tree_that_is_missing_or_not_a_directory(
    tmp_path: Path,
) -> None:
    regular = tmp_path / "docs"
    regular.write_bytes(b"not a directory")

    with pytest.raises(FoundryInputError, match="missing or unsafe: docs"):
        digest_artifact(regular, "tree", "docs")
    with pytest.raises(FoundryInputError, match="missing or unsafe: docs"):
        digest_artifact(tmp_path / "absent", "tree", "docs")


def test_digest_artifact_digests_a_tree_from_sorted_relative_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "docs"
    (root / "nested").mkdir(parents=True)
    (root / "b.md").write_bytes(b"second")
    (root / "a.md").write_bytes(b"first")
    (root / "nested" / "c.md").write_bytes(b"third")

    expected = hashlib.sha256(
        json.dumps(
            [
                ("a.md", _digest(b"first")),
                ("b.md", _digest(b"second")),
                ("nested/c.md", _digest(b"third")),
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert digest_artifact(root, "tree", "docs") == expected


def test_digest_artifact_tree_digest_ignores_directory_entries_themselves(
    tmp_path: Path,
) -> None:
    """An added empty directory carries no bytes, so it must not move the digest."""
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.md").write_bytes(b"first")
    before = digest_artifact(root, "tree", "docs")

    (root / "empty").mkdir()

    assert digest_artifact(root, "tree", "docs") == before


def test_digest_artifact_rejects_a_symlink_inside_a_tree(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"secret")
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.md").write_bytes(b"first")
    (root / "leak.md").symlink_to(outside)

    with pytest.raises(FoundryInputError, match="unsafe artifact path: docs"):
        digest_artifact(root, "tree", "docs")


def test_digest_artifact_rejects_a_non_file_inside_a_tree(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    os.mkfifo(root / "pipe")

    with pytest.raises(FoundryInputError, match="contains a non-file: docs"):
        digest_artifact(root, "tree", "docs")


def test_digest_artifact_reports_an_unreadable_tree_entry_as_input_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.md").write_bytes(b"first")

    def fail_read(*_args: object, **_kwargs: object) -> bytes:
        raise OSError("device is gone")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(FoundryInputError, match="cannot read artifact: docs"):
        digest_artifact(root, "tree", "docs")
