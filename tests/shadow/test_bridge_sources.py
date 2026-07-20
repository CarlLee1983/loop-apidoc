from __future__ import annotations

from datetime import datetime, timezone

import pytest

from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
    UrlSource,
)
from loop_apidoc.shadow.bridge import build_evidence


NOW = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)


def _local(
    relative_path: str = "manual.md",
    *,
    digest: str = "a" * 64,
    status: ProcessingStatus = ProcessingStatus.PENDING,
    supported: bool = True,
) -> LocalSource:
    return LocalSource(
        relative_path=relative_path,
        mime_type="text/markdown",
        source_format=SourceFormat.MARKDOWN,
        size_bytes=10,
        sha256=digest,
        scanned_at=NOW,
        supported=supported,
        status=status,
    )


def _url(
    url: str = "https://docs.example.test/api",
    *,
    digest: str | None = "b" * 64,
    snapshot_file: str | None = None,
) -> UrlSource:
    return UrlSource(
        url=url,
        fetched_at=NOW,
        http_status=200,
        content_sha256=digest,
        snapshot_file=snapshot_file,
    )


def _manifest(
    *,
    root: str = "/sources",
    local_sources: list[LocalSource] | None = None,
    url_sources: list[UrlSource] | None = None,
) -> Manifest:
    return Manifest(
        sources_root=root,
        generated_at=NOW,
        local_sources=local_sources or [],
        url_sources=url_sources or [],
    )


def test_source_set_identity_ignores_absolute_root_and_manifest_order():
    first_local = _local("a.md", digest="1" * 64)
    second_local = _local("b.md", digest="2" * 64)

    first = build_evidence(
        _manifest(root="/one", local_sources=[second_local, first_local]), NOW
    )
    second = build_evidence(
        _manifest(root="/two", local_sources=[first_local, second_local]), NOW
    )

    assert first.source_set == second.source_set
    assert first.source_set.id.startswith("source-set-")
    assert len(first.source_set.version) == 64
    assert [source.locator for source in first.source_set.sources] == ["a.md", "b.md"]


def test_usable_local_source_maps_to_one_whole_fragment():
    source = _local()

    built = build_evidence(_manifest(local_sources=[source]), NOW)

    descriptor = built.source_set.sources[0]
    artifact = built.evidence.artifacts[0]
    fragment = built.evidence.fragments[0]
    assert descriptor.kind == "file"
    assert descriptor.locator == "manual.md"
    assert descriptor.media_type == "text/markdown"
    assert artifact.source_id == descriptor.id
    assert artifact.content_digest == source.sha256
    assert artifact.acquired_at == NOW
    assert fragment.source_artifact_id == artifact.id
    assert fragment.fragment_digest == source.sha256
    assert fragment.locator == "whole"
    assert built.resolve_citation("manual.md") == (fragment.id,)


def test_url_without_content_digest_has_descriptor_but_no_artifact():
    source = _url(digest=None)

    built = build_evidence(_manifest(url_sources=[source]), NOW)

    assert built.source_set.sources[0].kind == "url"
    assert built.source_set.sources[0].locator == source.url
    assert built.source_set.sources[0].media_type is None
    assert built.evidence.artifacts == ()
    assert built.evidence.fragments == ()
    assert built.resolve_citation(source.url) == ()


def test_url_with_digest_maps_to_whole_fragment_without_invented_media_type():
    source = _url()

    built = build_evidence(_manifest(url_sources=[source]), NOW)

    artifact = built.evidence.artifacts[0]
    fragment = built.evidence.fragments[0]
    assert artifact.content_digest == source.content_sha256
    assert artifact.media_type == "application/octet-stream"
    assert artifact.acquisition_metadata == (("url", source.url),)
    assert built.resolve_citation(source.url) == (fragment.id,)


def test_url_snapshot_allows_url_to_resolve_to_local_fragment():
    snapshot = _local("snapshot.md", digest="c" * 64)
    source = _url(digest=None, snapshot_file="snapshot.md")

    built = build_evidence(
        _manifest(local_sources=[snapshot], url_sources=[source]), NOW
    )

    local_refs = built.resolve_citation("snapshot.md")
    assert local_refs
    assert built.resolve_citation(source.url) == local_refs


def test_url_snapshot_with_own_digest_resolves_to_url_and_local_fragments():
    snapshot = _local("snapshot.md", digest="c" * 64)
    source = _url(digest="d" * 64, snapshot_file="snapshot.md")

    built = build_evidence(
        _manifest(local_sources=[snapshot], url_sources=[source]), NOW
    )

    assert len(built.resolve_citation(source.url)) == 2
    assert set(built.resolve_citation("snapshot.md")) <= set(
        built.resolve_citation(source.url)
    )


@pytest.mark.parametrize(
    ("status", "supported"),
    [
        (ProcessingStatus.IGNORED, True),
        (ProcessingStatus.DUPLICATE, True),
        (ProcessingStatus.UNREADABLE, True),
        (ProcessingStatus.UNSUPPORTED, False),
    ],
)
def test_unusable_local_sources_never_become_descriptors_or_evidence(
    status: ProcessingStatus, supported: bool
):
    source = _local(status=status, supported=supported)

    built = build_evidence(_manifest(local_sources=[source]), NOW)

    assert built.source_set.sources == ()
    assert built.evidence.artifacts == ()
    assert built.evidence.fragments == ()
    assert built.resolve_citation(source.relative_path) == ()


def test_unusable_state_changes_source_set_identity():
    usable = build_evidence(_manifest(local_sources=[_local()]), NOW)
    ignored = build_evidence(
        _manifest(local_sources=[_local(status=ProcessingStatus.IGNORED)]), NOW
    )

    assert usable.source_set.version != ignored.source_set.version


def test_conflicting_duplicate_url_is_deterministic_and_not_groundable():
    first = _url(digest="1" * 64)
    second = _url(digest="2" * 64)

    forward = build_evidence(_manifest(url_sources=[first, second]), NOW)
    reverse = build_evidence(_manifest(url_sources=[second, first]), NOW)

    assert forward.source_set == reverse.source_set
    assert forward.evidence == reverse.evidence
    assert len(forward.source_set.sources) == 1
    assert forward.evidence.artifacts == ()
    assert forward.resolve_citation(first.url) == ()
    assert forward.diagnostics[0].code == "SOURCE_LOCATOR_AMBIGUOUS"
    assert forward.diagnostics[0].manifest_source == first.url


def test_identical_duplicate_url_is_deduplicated():
    source = _url(digest="3" * 64)

    built = build_evidence(_manifest(url_sources=[source, source.model_copy()]), NOW)

    assert len(built.source_set.sources) == 1
    assert len(built.evidence.artifacts) == 1
    assert len(built.evidence.fragments) == 1
