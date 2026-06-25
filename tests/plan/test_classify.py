from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.classify import classify_item, match_manifest_source
from loop_apidoc.plan.models import PlanItemStatus


def _manifest() -> Manifest:
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return Manifest(
        sources_root="/src",
        generated_at=now,
        local_sources=[
            LocalSource(relative_path="docs/api.pdf", mime_type="application/pdf",
                        source_format=SourceFormat.PDF, size_bytes=1, sha256="x",
                        scanned_at=now, supported=True, status=ProcessingStatus.PENDING),
        ],
    )


def test_match_by_basename():
    assert match_manifest_source("see api.pdf page 4", _manifest()) == "docs/api.pdf"


def test_match_none_when_absent():
    assert match_manifest_source("from the spec", _manifest()) is None
    assert match_manifest_source(None, _manifest()) is None


def test_classify_supported_when_matched():
    status, cite = classify_item(
        "api.pdf §2", query_id="05-initial", answer_path="answers/05-initial.txt",
        manifest=_manifest(),
    )
    assert status is PlanItemStatus.SUPPORTED
    assert cite.manifest_source == "docs/api.pdf"
    assert cite.locator == "api.pdf §2"
    assert cite.query_id == "05-initial"


def test_classify_unverified_when_unmatched_or_missing():
    status, cite = classify_item(
        "internal wiki", query_id="05-initial", answer_path="answers/05-initial.txt",
        manifest=_manifest(),
    )
    assert status is PlanItemStatus.UNVERIFIED
    assert cite.manifest_source is None

    status2, cite2 = classify_item(
        None, query_id="05-initial", answer_path="answers/05-initial.txt",
        manifest=_manifest(),
    )
    assert status2 is PlanItemStatus.UNVERIFIED
    assert cite2.locator is None
