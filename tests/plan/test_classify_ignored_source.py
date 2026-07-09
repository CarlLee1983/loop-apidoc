from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.classify import sole_source

_AT = datetime(2026, 7, 9, tzinfo=timezone.utc)


def _source(path: str, status: ProcessingStatus, supported: bool) -> LocalSource:
    return LocalSource(
        relative_path=path,
        mime_type="text/markdown",
        source_format=SourceFormat.MARKDOWN,
        size_bytes=1,
        sha256="a" * 64,
        scanned_at=_AT,
        supported=supported,
        status=status,
    )


def test_ignored_source_does_not_break_single_document_attribution():
    """一份 README 被略過後，manifest 仍應塌縮成單一文件，
    否則所有不含檔名的 locator 會突然全變 unverified（issue #1 的觸發器）。"""
    manifest = Manifest(
        sources_root="/s",
        generated_at=_AT,
        local_sources=[
            _source("README.md", ProcessingStatus.IGNORED, supported=False),
            _source("spec.pdf", ProcessingStatus.PENDING, supported=True),
        ],
    )

    assert sole_source(manifest) == "spec.pdf"
