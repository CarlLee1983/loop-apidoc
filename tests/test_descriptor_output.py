from __future__ import annotations

import os
from pathlib import Path

import pytest

import loop_apidoc.descriptor_output as descriptor_output
from loop_apidoc.descriptor_output import (
    DescriptorOutputError,
    output_path_from_fd,
)


def _directory_fd(path: Path) -> int:
    return os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )


def test_rejects_nonempty_stage_before_yielding_an_output_root(tmp_path: Path) -> None:
    """A caller cannot attach output ownership to a populated stage."""
    (tmp_path / "foreign.json").write_text("foreign", encoding="utf-8")
    directory_fd = _directory_fd(tmp_path)
    try:
        with pytest.raises(DescriptorOutputError, match="new output stage is not empty"):
            with output_path_from_fd(directory_fd):
                pass
    finally:
        os.close(directory_fd)


def test_rejects_a_regular_file_descriptor_as_an_output_stage(tmp_path: Path) -> None:
    """Only a pinned directory descriptor can establish the output namespace."""
    stage_file = tmp_path / "stage"
    stage_file.write_text("not a directory", encoding="utf-8")
    descriptor = os.open(stage_file, os.O_RDONLY)
    try:
        with pytest.raises(DescriptorOutputError, match="output descriptor is not a directory"):
            with output_path_from_fd(descriptor):
                pass
    finally:
        os.close(descriptor)


@pytest.mark.parametrize("unsafe", ["../escape.json", "/absolute.json", r"a\\b.json"])
def test_rejects_unsafe_relative_output_paths(tmp_path: Path, unsafe: str) -> None:
    """Output names cannot traverse or use a platform-ambiguous separator."""
    directory_fd = _directory_fd(tmp_path)
    try:
        with output_path_from_fd(directory_fd) as output:
            with pytest.raises(DescriptorOutputError, match="unsafe output path"):
                _ = output / unsafe
    finally:
        os.close(directory_fd)


def test_verify_ownership_rejects_an_unowned_stage_entry(tmp_path: Path) -> None:
    """Verification catches files introduced after the output root was pinned."""
    directory_fd = _directory_fd(tmp_path)
    try:
        with output_path_from_fd(directory_fd) as output:
            (output / "manifest.json").write_text("trusted", encoding="utf-8")
            (tmp_path / "foreign.json").write_text("foreign", encoding="utf-8")

            with pytest.raises(DescriptorOutputError, match="output stage namespace changed"):
                output.verify_ownership()
    finally:
        os.close(directory_fd)


def test_verify_ownership_rejects_a_replaced_owned_directory(tmp_path: Path) -> None:
    """A same-name directory replacement cannot inherit output ownership."""
    stage = tmp_path / "stage"
    stage.mkdir()
    directory_fd = _directory_fd(stage)
    try:
        with output_path_from_fd(directory_fd) as output:
            (output / "artifacts").mkdir()
            # Keep the displaced inode alive outside the output stage.  Removing
            # it would allow Linux to reuse the same inode for the replacement.
            os.rename(stage / "artifacts", tmp_path / "replaced-artifacts")
            (stage / "artifacts").mkdir()

            with pytest.raises(DescriptorOutputError, match="output directory identity changed"):
                output.verify_ownership()
    finally:
        os.close(directory_fd)


def test_verify_ownership_rejects_a_replaced_owned_file(tmp_path: Path) -> None:
    """A same-name regular file replacement cannot inherit output ownership."""
    directory_fd = _directory_fd(tmp_path)
    try:
        with output_path_from_fd(directory_fd) as output:
            (output / "manifest.json").write_text("trusted", encoding="utf-8")
            replacement = tmp_path / "replacement.json"
            replacement.write_text("foreign", encoding="utf-8")
            os.replace(replacement, tmp_path / "manifest.json")

            with pytest.raises(DescriptorOutputError, match="output file identity changed"):
                output.verify_ownership()
    finally:
        os.close(directory_fd)


def test_context_close_refuses_late_output_writes(tmp_path: Path) -> None:
    """The output root becomes unusable as soon as its context has closed."""
    directory_fd = _directory_fd(tmp_path)
    try:
        with output_path_from_fd(directory_fd) as output:
            target = output / "manifest.json"

        with pytest.raises(DescriptorOutputError, match="output descriptor is closed"):
            target.write_text("late", encoding="utf-8")
    finally:
        os.close(directory_fd)


def test_output_root_preserves_directory_only_path_semantics(tmp_path: Path) -> None:
    directory_fd = _directory_fd(tmp_path)
    try:
        with output_path_from_fd(directory_fd) as output:
            assert output.parent is output
            output.mkdir(exist_ok=True)
            with pytest.raises(FileExistsError, match="root already exists"):
                output.mkdir()
            with pytest.raises(IsADirectoryError, match="has no file leaf"):
                output.write_text("not a file", encoding="utf-8")
    finally:
        os.close(directory_fd)


def test_write_rejects_an_unowned_parent_directory(tmp_path: Path) -> None:
    directory_fd = _directory_fd(tmp_path)
    try:
        with output_path_from_fd(directory_fd) as output:
            with pytest.raises(DescriptorOutputError, match="output directory is not owned"):
                (output / "nested" / "manifest.json").write_text(
                    "not allowed", encoding="utf-8"
                )
    finally:
        os.close(directory_fd)


def test_mkdir_rejects_a_directory_introduced_after_stage_ownership(tmp_path: Path) -> None:
    directory_fd = _directory_fd(tmp_path)
    try:
        with output_path_from_fd(directory_fd) as output:
            (tmp_path / "nested").mkdir()
            with pytest.raises(DescriptorOutputError, match="output directory is not owned"):
                (output / "nested").mkdir()
    finally:
        os.close(directory_fd)


def test_mkdir_exist_ok_rechecks_a_replaced_owned_directory(tmp_path: Path) -> None:
    directory_fd = _directory_fd(tmp_path)
    try:
        with output_path_from_fd(directory_fd) as output:
            nested = output / "nested"
            nested.mkdir()
            os.rename(tmp_path / "nested", tmp_path / "retired-nested")
            (tmp_path / "nested").mkdir()

            with pytest.raises(DescriptorOutputError, match="output directory identity changed"):
                nested.mkdir(exist_ok=True)
    finally:
        os.close(directory_fd)


def test_mkdir_rejects_a_new_directory_replaced_before_it_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The metadata sampled after mkdir must bind the directory that is opened."""
    directory_fd = _directory_fd(tmp_path)
    original_stat = descriptor_output.os.stat
    replaced = False

    def stat_then_replace(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal replaced
        result = original_stat(path, *args, **kwargs)  # type: ignore[arg-type]
        if path == "nested" and kwargs.get("dir_fd") is not None and not replaced:
            replaced = True
            parent_fd = kwargs["dir_fd"]
            assert isinstance(parent_fd, int)
            os.rename(
                "nested",
                "retired-nested",
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.mkdir("nested", dir_fd=parent_fd)
            nested_fd = os.open(
                "nested",
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                dir_fd=parent_fd,
            )
            try:
                foreign_fd = os.open(
                    "foreign.json",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=nested_fd,
                )
                os.close(foreign_fd)
            finally:
                os.close(nested_fd)
        return result

    monkeypatch.setattr(descriptor_output.os, "stat", stat_then_replace)
    try:
        with output_path_from_fd(directory_fd) as output:
            with pytest.raises(
                DescriptorOutputError, match="new output directory identity changed"
            ):
                (output / "nested").mkdir()
    finally:
        os.close(directory_fd)

    assert replaced
    assert (tmp_path / "nested" / "foreign.json").is_file()
    assert (tmp_path / "retired-nested").is_dir()


def test_mkdir_rejects_content_introduced_after_the_new_directory_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A post-open foreign entry makes the new stage directory untrusted."""
    directory_fd = _directory_fd(tmp_path)
    original_open = descriptor_output._open_named_directory
    filled = False

    def open_then_fill(parent_fd: int, name: str) -> int:
        nonlocal filled
        descriptor = original_open(parent_fd, name)
        if name == "nested" and not filled:
            filled = True
            foreign_fd = os.open(
                "foreign.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=descriptor,
            )
            os.close(foreign_fd)
        return descriptor

    monkeypatch.setattr(descriptor_output, "_open_named_directory", open_then_fill)
    try:
        with output_path_from_fd(directory_fd) as output:
            with pytest.raises(
                DescriptorOutputError, match="new output directory is not empty"
            ):
                (output / "nested").mkdir()
    finally:
        os.close(directory_fd)

    assert filled
    assert (tmp_path / "nested" / "foreign.json").is_file()


def test_verify_ownership_rejects_a_file_removed_after_namespace_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The final leaf open catches a deletion after the directory scan."""
    directory_fd = _directory_fd(tmp_path)
    original_listdir = descriptor_output.os.listdir
    removed = False
    try:
        with output_path_from_fd(directory_fd) as output:
            (output / "manifest.json").write_text("trusted", encoding="utf-8")

            def list_then_remove(path: object) -> list[str]:
                nonlocal removed
                entries = original_listdir(path)
                if not removed:
                    removed = True
                    (tmp_path / "manifest.json").unlink()
                return entries

            monkeypatch.setattr(descriptor_output.os, "listdir", list_then_remove)
            with pytest.raises(DescriptorOutputError, match="output stage namespace changed"):
                output.verify_ownership()
    finally:
        os.close(directory_fd)

    assert removed


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="requires POSIX FIFOs")
def test_verify_ownership_rejects_a_replaced_fifo_without_blocking(
    tmp_path: Path,
) -> None:
    """A post-write FIFO replacement must fail closed rather than hang review."""
    directory_fd = _directory_fd(tmp_path)
    try:
        with output_path_from_fd(directory_fd) as output:
            target = output / "manifest.json"
            target.write_text("trusted", encoding="utf-8")
            parent_fd, leaf = target._open_leaf_parent()
            try:
                os.unlink(leaf, dir_fd=parent_fd)
                os.mkfifo(leaf, 0o600, dir_fd=parent_fd)
            finally:
                os.close(parent_fd)

            with pytest.raises(DescriptorOutputError, match="output file identity changed"):
                output.verify_ownership()
    finally:
        os.close(directory_fd)
