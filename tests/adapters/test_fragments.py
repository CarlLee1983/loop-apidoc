from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import httpx
import pymupdf
import pytest

from loop_apidoc.adapters.fragments import (
    FragmentRequest,
    acquire_fragment_bundle,
    parse_legacy_locator,
)
from loop_apidoc.domain.evidence import (
    CssSelectorLocator,
    FragmentPrecision,
    JsonPointerLocator,
    LineRangeLocator,
    PageLocator,
    SourceDescriptor,
    SourceSet,
    TableCellLocator,
    UnresolvedLocator,
    XPathLocator,
    fragment_digest,
)
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
    UrlSource,
)
from loop_apidoc.source_facts.markdown import scan_markdown
from loop_apidoc.source_facts.models import FactIndex


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("manual.pdf p.12", PageLocator(page=12)),
        (
            "spec.md lines 10-14",
            LineRangeLocator(start_line=10, end_line=14),
        ),
        (
            "openapi.json#/paths/~1payments/post",
            JsonPointerLocator(pointer="/paths/~1payments/post"),
        ),
        ("css:#payments", CssSelectorLocator(selector="#payments")),
        (
            "xpath://main/section[2]",
            XPathLocator(expression="//main/section[2]"),
        ),
    ],
)
def test_legacy_locator_parser_accepts_only_explicit_grammars(raw, expected):
    assert parse_legacy_locator(raw) == expected


def test_ambiguous_legacy_locator_is_unresolved():
    locator = parse_legacy_locator("see the payment section")

    assert isinstance(locator, UnresolvedLocator)


def _local_source(
    relative_path: str,
    source_format: SourceFormat,
    content: bytes,
) -> LocalSource:
    return LocalSource(
        relative_path=relative_path,
        mime_type=None,
        source_format=source_format,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        scanned_at=NOW,
        supported=True,
        status=ProcessingStatus.PENDING,
    )


def _source_set(source_id: str, locator: str, media_type: str) -> SourceSet:
    return SourceSet(
        id="sources",
        version="1",
        sources=(
            SourceDescriptor(
                id=source_id,
                kind="file",
                locator=locator,
                media_type=media_type,
            ),
        ),
    )


def test_markdown_table_cell_fragment_hashes_only_the_cell(tmp_path):
    text = """## POST /payments

| Name | Type | Required |
| --- | --- | --- |
| amount | integer | Y |
"""
    source = tmp_path / "manual.md"
    source.write_text(text, encoding="utf-8")
    manifest = Manifest(
        sources_root=str(tmp_path),
        generated_at=NOW,
        local_sources=[
            _local_source("manual.md", SourceFormat.MARKDOWN, source.read_bytes())
        ],
    )
    facts = FactIndex(sources=[scan_markdown("manual.md", text)])

    bundle = acquire_fragment_bundle(
        _source_set("manual", "manual.md", "text/markdown"),
        manifest,
        facts,
        (),
        NOW,
    )

    cell = next(
        fragment
        for fragment in bundle.fragments
        if isinstance(fragment.locator, TableCellLocator)
        and fragment.locator.column_name == "Required"
    )
    assert cell.normalized_excerpt == "Y"
    assert cell.fragment_digest == fragment_digest("Y")
    assert cell.parent_fragment_id is not None


def test_json_pointer_fragment_uses_canonical_selected_value(tmp_path):
    payload = {"components": {"schemas": {"Id": {"type": "string"}}}}
    source = tmp_path / "openapi.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    manifest = Manifest(
        sources_root=str(tmp_path),
        generated_at=NOW,
        local_sources=[
            _local_source(
                "openapi.json",
                SourceFormat.OPENAPI_JSON,
                source.read_bytes(),
            )
        ],
    )

    bundle = acquire_fragment_bundle(
        _source_set("openapi", "openapi.json", "application/json"),
        manifest,
        FactIndex(),
        (
            FragmentRequest(
                source_id="openapi",
                locator=JsonPointerLocator(pointer="/components/schemas/Id"),
            ),
        ),
        NOW,
    )

    fragment = next(
        item
        for item in bundle.fragments
        if isinstance(item.locator, JsonPointerLocator)
    )
    assert fragment.semantic_value == {"type": "string"}
    assert fragment.normalized_excerpt == '{"type":"string"}'


def test_line_range_fragment_is_exact_child_of_document(tmp_path):
    source = tmp_path / "manual.md"
    source.write_text("one\ntwo\nthree\n", encoding="utf-8")
    manifest = Manifest(
        sources_root=str(tmp_path),
        generated_at=NOW,
        local_sources=[
            _local_source("manual.md", SourceFormat.MARKDOWN, source.read_bytes())
        ],
    )

    bundle = acquire_fragment_bundle(
        _source_set("manual", "manual.md", "text/markdown"),
        manifest,
        FactIndex(),
        (
            FragmentRequest(
                source_id="manual",
                locator=LineRangeLocator(start_line=2, end_line=3),
            ),
        ),
        NOW,
    )

    fragment = next(
        item
        for item in bundle.fragments
        if isinstance(item.locator, LineRangeLocator)
    )
    assert fragment.normalized_excerpt == "two\nthree"
    assert fragment.precision is FragmentPrecision.EXACT
    assert fragment.parent_fragment_id is not None


def test_pdf_page_fragment_contains_only_requested_page(tmp_path):
    source = tmp_path / "manual.pdf"
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "FIRST PAGE")
    document.new_page().insert_text((72, 72), "SECOND PAGE")
    document.save(source)
    document.close()
    content = source.read_bytes()
    manifest = Manifest(
        sources_root=str(tmp_path),
        generated_at=NOW,
        local_sources=[_local_source("manual.pdf", SourceFormat.PDF, content)],
    )

    bundle = acquire_fragment_bundle(
        _source_set("manual", "manual.pdf", "application/pdf"),
        manifest,
        FactIndex(),
        (FragmentRequest(source_id="manual", locator=PageLocator(page=2)),),
        NOW,
    )

    page = next(
        fragment
        for fragment in bundle.fragments
        if isinstance(fragment.locator, PageLocator)
    )
    artifact = bundle.artifacts[0]
    assert "SECOND PAGE" in (page.normalized_excerpt or "")
    assert "FIRST PAGE" not in (page.normalized_excerpt or "")
    assert page.fragment_digest != artifact.content_digest
    assert page.parent_fragment_id is not None


def test_url_without_local_snapshot_is_never_fetched(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *_args, **_kwargs: pytest.fail("network used"),
    )
    source_set = SourceSet(
        id="sources",
        version="1",
        sources=(
            SourceDescriptor(
                id="remote",
                kind="url",
                locator="https://example.test/api",
                media_type="text/html",
            ),
        ),
    )
    manifest = Manifest(
        sources_root=".",
        generated_at=NOW,
        url_sources=[
            UrlSource(
                url="https://example.test/api",
                fetched_at=NOW,
                http_status=200,
            )
        ],
    )

    bundle = acquire_fragment_bundle(
        source_set,
        manifest,
        FactIndex(),
        (),
        NOW,
    )

    assert bundle.fragments
    assert all(
        fragment.precision is not FragmentPrecision.EXACT
        for fragment in bundle.fragments
    )
