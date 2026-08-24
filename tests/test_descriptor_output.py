from __future__ import annotations

import os
from pathlib import Path

import pytest

from loop_apidoc.descriptor_output import (
    DescriptorOutputError,
    output_path_from_fd,
)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="requires POSIX FIFOs")
def test_verify_ownership_rejects_a_replaced_fifo_without_blocking(
    tmp_path: Path,
) -> None:
    """A post-write FIFO replacement must fail closed rather than hang review."""
    directory_fd = os.open(
        tmp_path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
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
