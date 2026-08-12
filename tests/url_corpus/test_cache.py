from __future__ import annotations

import httpx
import pytest

from loop_apidoc.url_catalog import CatalogNode, UrlCatalog
from loop_apidoc.url_corpus import cache_catalog_pages


def test_cache_catalog_pages_preserves_raw_evidence_and_writes_compact_page_cards(tmp_path):
    catalog = UrlCatalog(
        entry_url="https://docs.example.com/transfer/introduction",
        nodes=[
            CatalogNode(url="https://docs.example.com/transfer/a", title="A"),
            CatalogNode(url="https://docs.example.com/transfer/b", title="B"),
        ],
    )
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        body = f"""
        <aside>Repeated navigation</aside>
        <main><h1>{request.url.path[-1].upper()}</h1><p>Action 19</p></main>
        """
        return httpx.Response(200, text=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        corpus = cache_catalog_pages(catalog, tmp_path, client=client)

    assert requested == ["https://docs.example.com/transfer/a", "https://docs.example.com/transfer/b"]
    assert [page.title for page in corpus.pages] == ["A", "B"]
    assert all(page.status == "fetched" for page in corpus.pages)
    assert all((tmp_path / page.raw_file).read_text(encoding="utf-8") for page in corpus.pages)
    assert all("Action 19" in (tmp_path / page.body_file).read_text(encoding="utf-8") for page in corpus.pages)
    assert all("Repeated navigation" not in (tmp_path / page.body_file).read_text(encoding="utf-8") for page in corpus.pages)
    assert all(page.entities == ["action:19"] for page in corpus.pages)


def test_cache_catalog_pages_stores_a_markdown_source_verbatim_without_html_normalization(tmp_path):
    catalog = UrlCatalog(
        entry_url="https://hackmd.io/GExmbK-TRfejmexd-_X7Pw",
        nodes=[CatalogNode(url="https://hackmd.io/GExmbK-TRfejmexd-_X7Pw", title="Entry page")],
    )
    requested: list[str] = []
    markdown = "# ATG API\n\n## GET /games\n\n| Field | Type |\n| --- | --- |\n| provider | string |\n"

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, text=markdown)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        corpus = cache_catalog_pages(catalog, tmp_path, client=client)

    assert requested == ["https://hackmd.io/GExmbK-TRfejmexd-_X7Pw/download"]
    page = corpus.pages[0]
    assert page.status == "fetched"
    assert page.raw_file.endswith(".md")
    # 正文必須逐字保留 Markdown（表格／換行），HTML 正規化會把它們壓成單行而遺失欄位表
    assert (tmp_path / page.body_file).read_text(encoding="utf-8") == markdown
    assert page.title == "ATG API"
    assert page.headings == ["ATG API", "GET /games"]


def test_cache_catalog_pages_counts_anchored_sections_as_one_document_for_max_pages(tmp_path):
    catalog = UrlCatalog(
        entry_url="https://docs.example.com/transfer",
        nodes=[
            CatalogNode(url="https://docs.example.com/transfer", title="API", anchor="api"),
            CatalogNode(
                url="https://docs.example.com/transfer", title="Errors", anchor="errors"
            ),
        ],
    )
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, text="<main><h1>Transfer</h1></main>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        corpus = cache_catalog_pages(catalog, tmp_path, client=client, max_pages=1)

    assert requested == ["https://docs.example.com/transfer"]
    assert [section.anchor for section in corpus.pages[0].sections] == ["api", "errors"]


def test_cache_catalog_pages_rejects_too_many_unique_documents_before_writing(tmp_path):
    catalog = UrlCatalog(
        entry_url="https://docs.example.com/transfer/a",
        nodes=[
            CatalogNode(url="https://docs.example.com/transfer/a", title="A"),
            CatalogNode(url="https://docs.example.com/transfer/b", title="B"),
        ],
    )
    requested: list[str] = []
    output = tmp_path / "corpus"

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, text="<main><h1>Transfer</h1></main>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(
            ValueError,
            match=r"^catalog has 2 unique documents, above max_pages=1$",
        ):
            cache_catalog_pages(catalog, output, client=client, max_pages=1)

    assert requested == []
    assert not output.exists()
