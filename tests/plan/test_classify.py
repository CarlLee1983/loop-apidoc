from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
    UrlSource,
)
from loop_apidoc.plan.classify import classify_item, match_manifest_source, sole_source
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


def _manifest_with(rel: str) -> Manifest:
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return Manifest(
        sources_root="/src", generated_at=now,
        local_sources=[
            LocalSource(relative_path=rel, mime_type="application/json",
                        source_format=SourceFormat.OPENAPI_JSON, size_bytes=1, sha256="x",
                        scanned_at=now, supported=True, status=ProcessingStatus.PENDING),
        ],
    )


def test_match_by_basename():
    assert match_manifest_source("see api.pdf page 4", _manifest()) == "docs/api.pdf"


def test_match_by_full_relative_path():
    assert match_manifest_source("from docs/api.pdf §3", _manifest()) == "docs/api.pdf"


def test_match_basename_with_trailing_punctuation():
    assert match_manifest_source("cited in api.pdf.", _manifest()) == "docs/api.pdf"
    assert match_manifest_source("(api.pdf)", _manifest()) == "docs/api.pdf"


def test_no_false_positive_on_embedded_basename():
    # "v1.json" must NOT match a locator mentioning the unrelated "specv1.json".
    m = _manifest_with("v1.json")
    assert match_manifest_source("see specv1.json reference", m) is None
    assert match_manifest_source("openapiv1.json", m) is None


def test_no_false_positive_on_substring_prefix():
    m = _manifest_with("api.pdf")
    assert match_manifest_source("myapi.pdf was used", m) is None


def test_match_basename_with_spaces():
    m = _manifest_with("docs/API Reference.pdf")
    assert match_manifest_source("see API Reference.pdf page 2", m) == "docs/API Reference.pdf"
    assert match_manifest_source("from docs/API Reference.pdf", m) == "docs/API Reference.pdf"


def test_spaced_filename_still_rejects_embedded_substring():
    m = _manifest_with("Reference.pdf")
    # "Reference.pdf" must not match inside "APIReference.pdf"
    assert match_manifest_source("the APIReference.pdf doc", m) is None


def test_match_basename_inside_fuller_path():
    # A citation that spells out an absolute/fuller path must still match by
    # basename: the `/` before "api.pdf" is a path boundary, not a token char.
    assert match_manifest_source("/src/docs/api.pdf", _manifest()) == "docs/api.pdf"
    assert match_manifest_source("see /home/user/docs/api.pdf", _manifest()) == "docs/api.pdf"


def test_match_relative_path_inside_fuller_path():
    m = _manifest_with("docs/api.json")
    assert match_manifest_source("/src/docs/api.json", m) == "docs/api.json"


def test_no_false_positive_on_embedded_basename_after_slash_is_word_char():
    # The `/` relaxation must not reopen the word-char false positive.
    m = _manifest_with("v1.json")
    assert match_manifest_source("dir/specv1.json", m) is None


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


def _multi_manifest() -> Manifest:
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return Manifest(
        sources_root="/src", generated_at=now,
        local_sources=[
            LocalSource(relative_path="docs/api.pdf", mime_type="application/pdf",
                        source_format=SourceFormat.PDF, size_bytes=1, sha256="x",
                        scanned_at=now, supported=True, status=ProcessingStatus.PENDING),
            LocalSource(relative_path="docs/extra.pdf", mime_type="application/pdf",
                        source_format=SourceFormat.PDF, size_bytes=1, sha256="y",
                        scanned_at=now, supported=True, status=ProcessingStatus.PENDING),
        ],
    )


def test_classify_unverified_when_unmatched_or_missing_with_multiple_sources():
    # With >1 source we cannot disambiguate, so an unmatched/absent locator stays
    # UNVERIFIED (single-source attribution does not apply).
    status, cite = classify_item(
        "internal wiki", query_id="05-initial", answer_path="answers/05-initial.txt",
        manifest=_multi_manifest(),
    )
    assert status is PlanItemStatus.UNVERIFIED
    assert cite.manifest_source is None

    status2, cite2 = classify_item(
        None, query_id="05-initial", answer_path="answers/05-initial.txt",
        manifest=_multi_manifest(),
    )
    assert status2 is PlanItemStatus.UNVERIFIED
    assert cite2.locator is None


def test_single_source_attributes_section_citation():
    # NotebookLM cites a section, not the filename; with exactly one source the
    # item is still SUPPORTED, attributed to that lone source.
    status, cite = classify_item(
        "section 4.2 MPG", query_id="06-initial",
        answer_path="answers/06-initial.txt", manifest=_manifest(),
    )
    assert status is PlanItemStatus.SUPPORTED
    assert cite.manifest_source == "docs/api.pdf"
    assert cite.locator == "section 4.2 MPG"


def test_single_source_attributes_missing_locator():
    # Most structured items carry no `source` field; a single-source notebook
    # still attributes them.
    status, cite = classify_item(
        None, query_id="05-initial", answer_path="answers/05-initial.txt",
        manifest=_manifest(),
    )
    assert status is PlanItemStatus.SUPPORTED
    assert cite.manifest_source == "docs/api.pdf"
    assert cite.locator is None


def test_single_source_ignores_unreadable_source():
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    manifest = Manifest(
        sources_root="/src", generated_at=now,
        local_sources=[
            LocalSource(relative_path="docs/api.pdf", mime_type="application/pdf",
                        source_format=SourceFormat.PDF, size_bytes=1, sha256="x",
                        scanned_at=now, supported=True,
                        status=ProcessingStatus.UNREADABLE),
        ],
    )
    status, cite = classify_item(
        None, query_id="05-initial", answer_path="answers/05-initial.txt",
        manifest=manifest,
    )
    assert status is PlanItemStatus.UNVERIFIED
    assert cite.manifest_source is None


def _now():
    return datetime(2026, 7, 4, tzinfo=timezone.utc)


def _local_src(rel: str, status=ProcessingStatus.PENDING) -> LocalSource:
    return LocalSource(
        relative_path=rel, mime_type="text/markdown", source_format=SourceFormat.MARKDOWN,
        size_bytes=1, sha256="x", scanned_at=_now(), supported=True, status=status,
    )


def _url_src(url: str, snapshot_file: str | None = None) -> UrlSource:
    return UrlSource(url=url, fetched_at=_now(), http_status=200, snapshot_file=snapshot_file)


def test_sole_source_collapses_url_pointing_to_local_snapshot():
    # 1 快照檔 + 1 entry URL(snapshot 指回該檔)→ 1 份文件 → 回傳本地檔 relative_path
    manifest = Manifest(
        sources_root="/src", generated_at=_now(),
        local_sources=[_local_src("overview.md")],
        url_sources=[_url_src("https://a.example/overview", snapshot_file="overview.md")],
    )
    assert sole_source(manifest) == "overview.md"


def test_sole_source_url_without_snapshot_counts_as_separate_document():
    # 無 snapshot_file → URL 另計一份 → 2 份文件 → None(維持現狀)
    manifest = Manifest(
        sources_root="/src", generated_at=_now(),
        local_sources=[_local_src("overview.md")],
        url_sources=[_url_src("https://a.example/overview", snapshot_file=None)],
    )
    assert sole_source(manifest) is None


def test_sole_source_snapshot_to_unusable_source_does_not_collapse():
    # snapshot_file 指向不可用(UNREADABLE)本地來源 → 該 URL 不被摺疊,另計一份
    manifest = Manifest(
        sources_root="/src", generated_at=_now(),
        local_sources=[_local_src("overview.md", status=ProcessingStatus.UNREADABLE)],
        url_sources=[_url_src("https://a.example/overview", snapshot_file="overview.md")],
    )
    # 本地來源不可用(0 份)+ URL 不摺疊(1 份)→ 恰好 1 份 → 回傳 URL
    assert sole_source(manifest) == "https://a.example/overview"


def test_sole_source_snapshot_to_unsupported_source_does_not_collapse():
    # snapshot_file 指向不可用(UNSUPPORTED)本地來源 → 該 URL 不被摺疊,另計一份
    manifest = Manifest(
        sources_root="/src", generated_at=_now(),
        local_sources=[_local_src("overview.md", status=ProcessingStatus.UNSUPPORTED)],
        url_sources=[_url_src("https://a.example/overview", snapshot_file="overview.md")],
    )
    # 本地來源不可用(0 份)+ URL 不摺疊(1 份)→ 恰好 1 份 → 回傳 URL
    assert sole_source(manifest) == "https://a.example/overview"


def test_sole_source_snapshot_to_duplicate_source_does_not_collapse():
    # snapshot_file 指向不可用(DUPLICATE)本地來源 → 該 URL 不被摺疊,另計一份
    manifest = Manifest(
        sources_root="/src", generated_at=_now(),
        local_sources=[_local_src("overview.md", status=ProcessingStatus.DUPLICATE)],
        url_sources=[_url_src("https://a.example/overview", snapshot_file="overview.md")],
    )
    # 本地來源不可用(0 份)+ URL 不摺疊(1 份)→ 恰好 1 份 → 回傳 URL
    assert sole_source(manifest) == "https://a.example/overview"


def test_sole_source_dangling_snapshot_reference_does_not_collapse():
    # snapshot_file 指向 manifest.local_sources 中根本不存在的 relative_path
    # (懸空引用)→ URL 摺疊目標不在可用集合中 → 不摺疊 → 連同另一份可用本地來源
    # 共 2 份文件 → None
    manifest = Manifest(
        sources_root="/src", generated_at=_now(),
        local_sources=[_local_src("overview.md")],
        url_sources=[_url_src("https://a.example/overview", snapshot_file="missing.md")],
    )
    assert sole_source(manifest) is None


def test_sole_source_multi_file_plus_url_still_none():
    manifest = Manifest(
        sources_root="/src", generated_at=_now(),
        local_sources=[_local_src("a.md"), _local_src("b.md")],
        url_sources=[_url_src("https://a.example/a", snapshot_file="a.md")],
    )
    # 摺疊後仍是 a.md + b.md = 2 份 → None(多來源 run 仍須嚴格比對)
    assert sole_source(manifest) is None
