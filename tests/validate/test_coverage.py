from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
    UrlSource,
)
from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.plan.models import PlanItemStatus
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


def _provenance(*sources: str) -> ProvenanceDocument:
    return ProvenanceDocument(
        notebook_url="",
        entries=[
            ProvenanceEntry(
                target=f"paths./{index}.get",
                status=PlanItemStatus.SUPPORTED,
                manifest_source=source,
            )
            for index, source in enumerate(sources)
        ],
    )


def test_supported_source_without_material_citation_is_warning() -> None:
    manifest = _manifest(
        _source("api.md", SourceFormat.MARKDOWN, ProcessingStatus.PENDING),
        _source("codes.pdf", SourceFormat.PDF, ProcessingStatus.PENDING),
    )

    issues = check_manifest_coverage(manifest, _provenance("api.md"))

    assert len(issues) == 1
    assert issues[0].code is IssueCode.SOURCE_UNVERIFIED
    assert issues[0].severity is Severity.WARNING
    assert issues[0].location == "codes.pdf"
    assert "實質引用" in issues[0].evidence


def test_successful_standalone_url_without_material_citation_is_warning() -> None:
    manifest = Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        url_sources=[
            UrlSource(
                url="https://docs.example.com/api",
                fetched_at=_NOW,
                http_status=200,
            )
        ],
    )

    issues = check_manifest_coverage(manifest, _provenance())

    assert len(issues) == 1
    assert issues[0].location == "https://docs.example.com/api"
    assert issues[0].severity is Severity.WARNING


def test_url_snapshot_is_not_counted_as_a_second_document() -> None:
    manifest = Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            _source("api.md", SourceFormat.MARKDOWN, ProcessingStatus.PENDING)
        ],
        url_sources=[
            UrlSource(
                url="https://docs.example.com/api",
                fetched_at=_NOW,
                http_status=200,
                snapshot_file="api.md",
            )
        ],
    )

    issues = check_manifest_coverage(manifest, _provenance("api.md"))

    assert issues == []


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


def test_an_unsupported_spreadsheet_is_told_what_to_do_next() -> None:
    """通則的 remedy 列了四種受支援格式,卻沒有一種是拿著 .xlsx 的人做得到的。"""
    manifest = _manifest(
        _source("codes.xlsx", SourceFormat.SPREADSHEET, ProcessingStatus.UNSUPPORTED)
    )
    issues = check_manifest_coverage(manifest)
    assert len(issues) == 1
    assert "Markdown 表格" in issues[0].suggested_fix
    # CSV 不在受支援副檔名裡,建議另存 CSV 等於把他送回同一個 unsupported。
    assert "CSV" not in issues[0].suggested_fix.upper()


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
