from __future__ import annotations

import os
from pathlib import Path

import pytest

from loop_apidoc.foundry import descriptor_tree, store
from loop_apidoc.foundry.models import FoundryInputError


def test_copy_tree_to_directory_copies_nested_regular_files_and_rolls_back_unsafe_input(
    tmp_path: Path,
) -> None:
    source = tmp_path / "candidate"
    (source / "nested").mkdir(parents=True)
    (source / "asset.json").write_text("{}", encoding="utf-8")
    (source / "nested" / "artifact.txt").write_text("payload", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    destination_fd = os.open(
        destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        descriptor_tree.copy_tree_to_directory(source, destination_fd, "published")
        assert (destination / "published" / "nested" / "artifact.txt").read_text(
            encoding="utf-8"
        ) == "payload"

        unsafe_source = tmp_path / "unsafe-candidate"
        unsafe_source.mkdir()
        (unsafe_source / "link").symlink_to(source / "asset.json")
        with pytest.raises(FoundryInputError, match="unsafe"):
            descriptor_tree.copy_tree_to_directory(
                unsafe_source, destination_fd, "unsafe"
            )
        assert not (destination / "unsafe").exists()
    finally:
        os.close(destination_fd)


def test_copy_tree_rejects_source_file_replaced_by_symlink_after_metadata_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "candidate"
    source.mkdir()
    payload = source / "payload.txt"
    payload.write_text("trusted", encoding="utf-8")
    external = tmp_path / "external.txt"
    external.write_text("attacker", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    destination_fd = os.open(
        destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    original_stat = descriptor_tree.os.stat
    replaced = False

    def stat_then_replace(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal replaced
        result = original_stat(path, *args, **kwargs)  # type: ignore[arg-type]
        is_payload = path == payload or (
            path == "payload.txt" and kwargs.get("dir_fd") is not None
        )
        if is_payload and not replaced:
            replaced = True
            payload.unlink()
            payload.symlink_to(external)
        return result

    monkeypatch.setattr(descriptor_tree.os, "stat", stat_then_replace)
    try:
        with pytest.raises(FoundryInputError, match="unsafe"):
            descriptor_tree.copy_tree_to_directory(source, destination_fd, "copied")
        assert replaced
        assert not (destination / "copied").exists()
    finally:
        os.close(destination_fd)


def test_copy_tree_rejects_source_directory_replaced_by_symlink_after_metadata_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "candidate"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (nested / "payload.txt").write_text("trusted", encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    (external / "payload.txt").write_text("attacker", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    destination_fd = os.open(
        destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    original_stat = descriptor_tree.os.stat
    replaced = False

    def stat_then_replace(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal replaced
        result = original_stat(path, *args, **kwargs)  # type: ignore[arg-type]
        is_nested = path == nested or (
            path == "nested" and kwargs.get("dir_fd") is not None
        )
        if is_nested and not replaced:
            replaced = True
            nested.rename(source / "moved-nested")
            nested.symlink_to(external, target_is_directory=True)
        return result

    monkeypatch.setattr(descriptor_tree.os, "stat", stat_then_replace)
    try:
        with pytest.raises(FoundryInputError, match="unsafe"):
            descriptor_tree.copy_tree_to_directory(source, destination_fd, "copied")
        assert replaced
        assert not (destination / "copied").exists()
    finally:
        os.close(destination_fd)


def test_publish_asset_publishes_once_without_replacing_existing_root(
    tmp_path: Path,
) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    staged = assets / ".stage"
    staged.mkdir()
    (staged / "asset.json").write_text("{}", encoding="utf-8")
    published = assets / "asset-1"

    outcome = store.publish_asset(staged, published)

    assert outcome.owned_root
    assert outcome.identity is not None
    assert (published / "asset.json").is_file()

    retry_stage = assets / ".retry-stage"
    retry_stage.mkdir()
    with pytest.raises(FoundryInputError, match="already exists"):
        store.publish_asset(retry_stage, published)
