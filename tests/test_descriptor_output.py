from __future__ import annotations

import os
from pathlib import Path

import pytest

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
    directory_fd = _directory_fd(tmp_path)
    try:
        with output_path_from_fd(directory_fd) as output:
            (output / "artifacts").mkdir()
            os.rename(tmp_path / "artifacts", tmp_path / "replaced-artifacts")
            os.rmdir(tmp_path / "replaced-artifacts")
            (tmp_path / "artifacts").mkdir()

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
