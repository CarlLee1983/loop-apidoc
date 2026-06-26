from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.validate.coverage import check_manifest_coverage
from loop_apidoc.validate.models import IssueCode, Severity

_NOW = datetime(2026, 6, 26, tzinfo=timezone.utc)


def _source(relative_path: str, fmt: SourceFormat, status: ProcessingStatus) -> LocalSource:
    return LocalSource(
        relative_path=relative_path,
        mime_type=None,
        source_format=fmt,
        size_bytes=10,
        sha256="abc",
        scanned_at=_NOW,
        supported=status not in (ProcessingStatus.UNSUPPORTED, ProcessingStatus.UNREADABLE),
        status=status,
    )


def _manifest(*sources: LocalSource) -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=list(sources),
    )


def test_unreadable_source_is_error() -> None:
    manifest = _manifest(
        _source("broken.pdf", SourceFormat.PDF, ProcessingStatus.UNREADABLE)
    )
    issues = check_manifest_coverage(manifest)
    assert len(issues) == 1
    assert issues[0].code is IssueCode.SOURCE_UNVERIFIED
    assert issues[0].severity is Severity.ERROR
    assert issues[0].location == "broken.pdf"


def test_unsupported_source_is_warning() -> None:
    manifest = _manifest(
        _source("logo.png", SourceFormat.UNKNOWN, ProcessingStatus.UNSUPPORTED)
    )
    issues = check_manifest_coverage(manifest)
    assert len(issues) == 1
    assert issues[0].code is IssueCode.SOURCE_UNVERIFIED
    assert issues[0].severity is Severity.WARNING
    assert issues[0].location == "logo.png"
    assert "unknown" in issues[0].evidence


def test_duplicate_source_is_not_surfaced() -> None:
    dup = _source("copy.md", SourceFormat.MARKDOWN, ProcessingStatus.DUPLICATE)
    dup.duplicate_of = "orig.md"
    assert check_manifest_coverage(_manifest(dup)) == []


def test_clean_manifest_has_no_coverage_issues() -> None:
    manifest = _manifest(
        _source("api.md", SourceFormat.MARKDOWN, ProcessingStatus.PENDING)
    )
    assert check_manifest_coverage(manifest) == []


def test_empty_manifest_has_no_coverage_issues() -> None:
    assert check_manifest_coverage(_manifest()) == []


def test_mixed_statuses_count_and_severity() -> None:
    manifest = _manifest(
        _source("broken.pdf", SourceFormat.PDF, ProcessingStatus.UNREADABLE),
        _source("logo.png", SourceFormat.UNKNOWN, ProcessingStatus.UNSUPPORTED),
        _source("copy.md", SourceFormat.MARKDOWN, ProcessingStatus.DUPLICATE),
        _source("api.md", SourceFormat.MARKDOWN, ProcessingStatus.PENDING),
    )
    issues = check_manifest_coverage(manifest)
    assert len(issues) == 2
    severities = {i.location: i.severity for i in issues}
    assert severities == {"broken.pdf": Severity.ERROR, "logo.png": Severity.WARNING}
    assert all(i.code is IssueCode.SOURCE_UNVERIFIED for i in issues)
