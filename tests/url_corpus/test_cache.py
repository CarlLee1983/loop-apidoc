from __future__ import annotations

import httpx

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
