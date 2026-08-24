from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

import loop_apidoc.adapters.local as local_adapter
from loop_apidoc.adapters.local import DirectoryArtifactSink, LocalFileSourceAdapter
from loop_apidoc.atomic_publish import DirectoryPublicationCollisionError
from loop_apidoc.core.artifacts import projection_content_address
from loop_apidoc.core.models import (
    ContractRelease,
    ReleaseStatus,
    SourceDescriptor,
    SourceSet,
    ValidationDecision,
    ValidationVerdict,
)
from loop_apidoc.domain.projections import Projection


def test_local_source_hashes_original_and_links_fragment(tmp_path):
    source = tmp_path / "manual.md"
    source.write_text("# API\nGET /health", encoding="utf-8")
    source_set = SourceSet(
        id="sources",
        version="1",
        sources=(
            SourceDescriptor(
                id="manual",
                kind="file",
                locator=str(source),
                media_type="text/markdown",
            ),
        ),
    )

    bundle = LocalFileSourceAdapter().acquire(source_set)

    assert (
        bundle.artifacts[0].content_digest
        == hashlib.sha256(source.read_bytes()).hexdigest()
    )
    assert bundle.fragments[0].source_artifact_id == bundle.artifacts[0].id


def test_local_source_rejects_an_unsupported_source_kind(tmp_path):
    source_set = SourceSet(
        id="sources",
        version="1",
        sources=(
            SourceDescriptor(
                id="remote",
                kind="url",
                locator=str(tmp_path / "manual.md"),
            ),
        ),
    )

    with pytest.raises(ValueError, match="unsupported"):
        LocalFileSourceAdapter().acquire(source_set)


def test_directory_artifact_sink_writes_compiled_values(tmp_path):
    sink = DirectoryArtifactSink(tmp_path)
    projections = (
        Projection(
            name="openapi.json",
            version="1",
            media_type="application/json",
            content=b'{"openapi":"3.1.0"}',
        ),
        Projection(
            name="schemas/card.json",
            version="1",
            media_type="application/json",
            content=b'{"type":"string"}',
        ),
    )

    refs = sink.publish(_approved_release(), projections)

    assert len(refs) == 2
    assert all(ref.startswith(str(tmp_path)) for ref in refs)
    assert tuple(Path(ref).read_bytes() for ref in refs) == tuple(
        projection.content for projection in projections
    )
    assert sink.publish(_approved_release(), projections) == refs


def test_directory_artifact_sink_rejects_unapproved_release(tmp_path):
    sink = DirectoryArtifactSink(tmp_path)
    projection = Projection(
        name="openapi.json",
        version="1",
        media_type="application/json",
        content=b'{}',
    )

    with pytest.raises(ValueError, match="approved"):
        sink.publish(
            _approved_release().model_copy(update={"status": ReleaseStatus.CANDIDATE}),
            (projection,),
        )


def test_directory_artifact_sink_rejects_empty_and_unsafe_projection_paths(tmp_path):
    sink = DirectoryArtifactSink(tmp_path)
    unsafe = Projection(
        name="../openapi.json",
        version="1",
        media_type="application/json",
        content=b"{}",
    )

    with pytest.raises(ValueError, match="at least one"):
        sink.publish(_approved_release(), ())
    with pytest.raises(ValueError, match="relative artifact path"):
        sink.publish(_approved_release(), (unsafe,))


def test_directory_artifact_sink_rejects_existing_destination_symlink(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    projection = Projection(
        name="openapi.json",
        version="1",
        media_type="application/json",
        content=b"{}",
    )
    (outside / projection.name).write_bytes(projection.content)
    destination = root / projection_content_address((projection,))
    destination.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        DirectoryArtifactSink(root).publish(_approved_release(), (projection,))


def test_directory_artifact_sink_rejects_nested_symlink_in_existing_artifact(
    tmp_path,
):
    root = tmp_path / "artifacts"
    projection = Projection(
        name="schemas/card.json",
        version="1",
        media_type="application/json",
        content=b'{"type":"string"}',
    )
    destination = root / projection_content_address((projection,))
    destination.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "card.json").write_bytes(projection.content)
    (destination / "schemas").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        DirectoryArtifactSink(root).publish(_approved_release(), (projection,))


def test_directory_artifact_sink_rejects_unexpected_empty_directory(tmp_path):
    root = tmp_path / "artifacts"
    projection = Projection(
        name="openapi.json",
        version="1",
        media_type="application/json",
        content=b"{}",
    )
    destination = root / projection_content_address((projection,))
    destination.mkdir(parents=True)
    (destination / projection.name).write_bytes(projection.content)
    (destination / "unexpected").mkdir()

    with pytest.raises(ValueError, match="does not match"):
        DirectoryArtifactSink(root).publish(_approved_release(), (projection,))


def test_directory_artifact_sink_rejects_mismatched_existing_content(tmp_path):
    root = tmp_path / "artifacts"
    projection = Projection(
        name="openapi.json",
        version="1",
        media_type="application/json",
        content=b"{}",
    )
    destination = root / projection_content_address((projection,))
    destination.mkdir(parents=True)
    (destination / projection.name).write_bytes(b'{"wrong":true}')

    with pytest.raises(ValueError, match="does not match"):
        DirectoryArtifactSink(root).publish(_approved_release(), (projection,))


def test_directory_artifact_sink_reuses_a_matching_preexisting_tree(tmp_path):
    root = tmp_path / "artifacts"
    projection = Projection(
        name="schemas/card.json",
        version="1",
        media_type="application/json",
        content=b'{"type":"string"}',
    )
    publication_id = projection_content_address((projection,))
    destination = root / publication_id
    child = destination / projection.name
    child.parent.mkdir(parents=True)
    child.write_bytes(projection.content)

    refs = DirectoryArtifactSink(root).publish(_approved_release(), (projection,))

    assert refs == (str(child),)


def test_directory_artifact_sink_rejects_an_existing_hard_link(tmp_path):
    root = tmp_path / "artifacts"
    projection = Projection(
        name="openapi.json",
        version="1",
        media_type="application/json",
        content=b"{}",
    )
    destination = root / projection_content_address((projection,))
    destination.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(projection.content)
    os.link(outside, destination / projection.name)

    with pytest.raises(ValueError, match="hard link"):
        DirectoryArtifactSink(root).publish(_approved_release(), (projection,))


def test_directory_artifact_sink_rejects_a_child_replaced_after_validation(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "artifacts"
    projection = Projection(
        name="openapi.json",
        version="1",
        media_type="application/json",
        content=b"{}",
    )
    destination = root / projection_content_address((projection,))
    destination.mkdir(parents=True)
    child = destination / projection.name
    child.write_bytes(projection.content)
    original_read = local_adapter._read_artifact_tree
    replaced = False

    def read_then_replace(
        directory_fd: int, prefix: tuple[str, ...] = ()
    ):
        nonlocal replaced
        result = original_read(directory_fd, prefix)
        if not prefix and not replaced:
            replaced = True
            child.rename(destination / "original-openapi.json")
            child.write_bytes(b"foreign")
        return result

    monkeypatch.setattr(local_adapter, "_read_artifact_tree", read_then_replace)

    with pytest.raises(ValueError, match="identity changed"):
        DirectoryArtifactSink(root).publish(_approved_release(), (projection,))


def test_directory_artifact_sink_rejects_a_symlinked_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "artifacts"
    root.symlink_to(outside, target_is_directory=True)
    projection = Projection(
        name="openapi.json",
        version="1",
        media_type="application/json",
        content=b"{}",
    )

    with pytest.raises(ValueError, match="non-symlink"):
        DirectoryArtifactSink(root).publish(_approved_release(), (projection,))


def test_directory_artifact_sink_retains_staging_after_a_publish_collision(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "artifacts"
    projection = Projection(
        name="openapi.json",
        version="1",
        media_type="application/json",
        content=b"{}",
    )
    publication_id = projection_content_address((projection,))
    original_publish = local_adapter.publish_directory_noreplace
    staged: Path | None = None

    def lose_the_race(
        staging: Path,
        destination: Path,
        *,
        parent_fd: int | None = None,
    ) -> None:
        nonlocal staged
        staged = root / staging.name
        destination_path = root / destination.name
        destination_path.mkdir()
        (destination_path / projection.name).write_bytes(projection.content)
        try:
            original_publish(staging, destination, parent_fd=parent_fd)
        except DirectoryPublicationCollisionError:
            raise

    monkeypatch.setattr(local_adapter, "publish_directory_noreplace", lose_the_race)

    refs = DirectoryArtifactSink(root).publish(_approved_release(), (projection,))

    assert refs == (str(root / publication_id / projection.name),)
    assert staged is not None
    assert (staged / projection.name).read_bytes() == projection.content


def test_directory_artifact_sink_rejects_a_replaced_destination_during_publish(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "artifacts"
    projection = Projection(
        name="openapi.json",
        version="1",
        media_type="application/json",
        content=b"{}",
    )
    original_publish = local_adapter.publish_directory_noreplace

    def replace_staging_then_publish(
        staging: Path,
        destination: Path,
        *,
        parent_fd: int | None = None,
    ) -> None:
        staging_path = root / staging.name
        staging_path.rename(root / "owned-staging")
        staging_path.mkdir()
        (staging_path / projection.name).write_bytes(b"foreign")
        original_publish(staging, destination, parent_fd=parent_fd)

    monkeypatch.setattr(
        local_adapter, "publish_directory_noreplace", replace_staging_then_publish
    )

    with pytest.raises(ValueError, match="identity changed"):
        DirectoryArtifactSink(root).publish(_approved_release(), (projection,))

    publication = root / projection_content_address((projection,))
    assert (publication / projection.name).read_bytes() == b"foreign"


def test_directory_artifact_sink_rejects_a_replaced_root_after_publish(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "artifacts"
    projection = Projection(
        name="openapi.json",
        version="1",
        media_type="application/json",
        content=b"{}",
    )
    original_publish = local_adapter.publish_directory_noreplace

    def publish_then_replace_root(
        staging: Path,
        destination: Path,
        *,
        parent_fd: int | None = None,
    ) -> None:
        original_publish(staging, destination, parent_fd=parent_fd)
        root.rename(tmp_path / "moved-artifacts")
        root.mkdir()

    monkeypatch.setattr(
        local_adapter, "publish_directory_noreplace", publish_then_replace_root
    )

    with pytest.raises(ValueError, match="root identity changed"):
        DirectoryArtifactSink(root).publish(_approved_release(), (projection,))


def test_directory_artifact_sink_does_not_delete_replaced_staging_after_publish(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "artifacts"
    projection = Projection(
        name="openapi.json",
        version="1",
        media_type="application/json",
        content=b"{}",
    )
    original_publish = local_adapter.publish_directory_noreplace
    recreated: Path | None = None

    def publish_then_recreate(
        staging: Path,
        destination: Path,
        *,
        parent_fd: int | None = None,
    ) -> None:
        nonlocal recreated
        original_publish(staging, destination, parent_fd=parent_fd)
        recreated = root / staging.name
        recreated.mkdir()
        (recreated / "foreign.txt").write_text("must survive", encoding="utf-8")

    monkeypatch.setattr(
        local_adapter, "publish_directory_noreplace", publish_then_recreate
    )

    DirectoryArtifactSink(root).publish(_approved_release(), (projection,))

    assert recreated is not None
    assert (recreated / "foreign.txt").read_text(encoding="utf-8") == "must survive"


def _approved_release() -> ContractRelease:
    return ContractRelease(
        release_id="release-1",
        contract_id="demo",
        contract_digest="a" * 64,
        source_set_id="sources",
        source_set_version="1",
        status=ReleaseStatus.APPROVED,
        validation=ValidationDecision(
            verdict=ValidationVerdict.ACCEPT,
            policy_profile="strict",
        ),
        runtime_identities=(),
        core_version="1",
        domain_version="1",
        policy_version="strict",
        projection_versions=(("openapi", "1"),),
        created_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
    )
