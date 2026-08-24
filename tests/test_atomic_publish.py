from __future__ import annotations

import os
from pathlib import Path

import pytest

import loop_apidoc.atomic_publish as atomic_publish


def test_publish_requires_staging_and_destination_to_share_a_parent(
    tmp_path: Path,
) -> None:
    staged = tmp_path / "staged"
    staged.mkdir()
    other_parent = tmp_path / "other"
    other_parent.mkdir()

    with pytest.raises(
        atomic_publish.DirectoryPublicationError, match="requires one parent"
    ):
        atomic_publish.publish_directory_noreplace(staged, other_parent / "published")

    assert staged.is_dir()


def test_publish_fails_closed_when_secure_directory_open_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(atomic_publish.os, "O_DIRECTORY", None)

    with pytest.raises(
        atomic_publish.DirectoryPublicationError, match="unavailable on this platform"
    ):
        atomic_publish.open_directory(tmp_path, "publication parent")


def test_open_directory_rejects_a_symlinked_publication_parent(tmp_path: Path) -> None:
    trusted_parent = tmp_path / "trusted"
    trusted_parent.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(trusted_parent, target_is_directory=True)

    with pytest.raises(
        atomic_publish.DirectoryPublicationError, match="not a real non-symlink directory"
    ):
        atomic_publish.open_directory(alias, "publication parent")


@pytest.mark.parametrize("prefix", ("", "../stage-", r"stage\\"))
def test_private_stage_name_allocation_rejects_unsafe_prefixes(
    tmp_path: Path, prefix: str
) -> None:
    parent_fd = atomic_publish.open_directory(tmp_path, "publication parent")
    try:
        with pytest.raises(
            atomic_publish.DirectoryPublicationError, match="unsafe private directory prefix"
        ):
            atomic_publish.create_owned_directory_relative(
                parent_fd, prefix=prefix, label="stage"
            )
    finally:
        os.close(parent_fd)


def test_private_stage_name_allocation_is_bounded_when_every_name_collides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_fd = atomic_publish.open_directory(tmp_path, "publication parent")

    def always_collide(*args: object, **kwargs: object) -> None:
        raise FileExistsError("injected collision")

    monkeypatch.setattr(atomic_publish.os, "mkdir", always_collide)
    try:
        with pytest.raises(
            atomic_publish.DirectoryPublicationError, match="cannot allocate private stage"
        ):
            atomic_publish.create_owned_directory_relative(
                parent_fd, prefix=".stage-", label="stage"
            )
    finally:
        os.close(parent_fd)


def test_publish_rejects_a_staging_name_that_no_longer_has_its_expected_identity(
    tmp_path: Path,
) -> None:
    staged = tmp_path / "staged"
    staged.mkdir()
    destination = tmp_path / "published"
    parent_fd = atomic_publish.open_directory(tmp_path, "publication parent")
    try:
        with pytest.raises(
            atomic_publish.DirectoryPublicationError, match="source identity changed"
        ):
            atomic_publish.publish_directory_noreplace(
                staged,
                destination,
                parent_fd=parent_fd,
                expected_source_identity=(0, 0),
            )
    finally:
        os.close(parent_fd)

    assert staged.is_dir()
    assert not destination.exists()


def test_publish_quarantines_a_result_that_fails_post_publish_verification(
    tmp_path: Path,
) -> None:
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "artifact.json").write_text("trusted", encoding="utf-8")
    destination = tmp_path / "published"

    def reject_published_stage() -> None:
        raise RuntimeError("injected post-publish verification failure")

    with pytest.raises(
        atomic_publish.DirectoryPublicationError,
        match="failed verification; retained outside the canonical run name",
    ):
        atomic_publish.publish_directory_noreplace(
            staged,
            destination,
            post_publish_verify=reject_published_stage,
        )

    assert not destination.exists()
    quarantines = list(tmp_path.glob(".published-rejected-*"))
    assert len(quarantines) == 1
    assert (quarantines[0] / "artifact.json").read_text(encoding="utf-8") == "trusted"


def test_publish_retains_the_canonical_entry_when_failed_verification_cannot_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = tmp_path / "staged"
    staged.mkdir()
    destination = tmp_path / "published"

    def reject_published_stage() -> None:
        raise RuntimeError("injected post-publish verification failure")

    def fail_quarantine(*_args: object, **_kwargs: object) -> str:
        raise OSError("injected quarantine failure")

    monkeypatch.setattr(atomic_publish, "_quarantine_untrusted_entry", fail_quarantine)
    with pytest.raises(
        atomic_publish.DirectoryPublicationError, match="could not be quarantined"
    ):
        atomic_publish.publish_directory_noreplace(
            staged,
            destination,
            post_publish_verify=reject_published_stage,
        )

    assert destination.is_dir()
    assert not list(tmp_path.glob(".published-rejected-*"))


def test_publish_fails_closed_when_the_platform_lacks_a_no_replace_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = tmp_path / "staged"
    staged.mkdir()
    destination = tmp_path / "published"
    monkeypatch.setattr(atomic_publish.sys, "platform", "unsupported")

    with pytest.raises(
        atomic_publish.DirectoryPublicationError, match="directory publication failed"
    ):
        atomic_publish.publish_directory_noreplace(staged, destination)

    assert staged.is_dir()
    assert not destination.exists()
