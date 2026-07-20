from __future__ import annotations

import hashlib

from loop_apidoc.adapters.local import DirectoryArtifactSink, LocalFileSourceAdapter
from loop_apidoc.core.models import SourceDescriptor, SourceSet
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


def test_directory_artifact_sink_writes_compiled_values(tmp_path):
    sink = DirectoryArtifactSink(tmp_path)
    projection = Projection(
        name="openapi.json",
        version="1",
        media_type="application/json",
        content=b'{"openapi":"3.1.0"}',
    )

    refs = sink.publish("release-1", (projection,))

    assert refs == (str(tmp_path / "release-1" / "openapi.json"),)
    assert (tmp_path / "release-1" / "openapi.json").read_bytes() == projection.content
