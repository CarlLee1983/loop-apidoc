from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.url_catalog import CatalogNode, UrlCatalog
from loop_apidoc.url_corpus import CorpusPage, UrlCorpus


runner = CliRunner()


def test_cache_url_pages_writes_a_local_corpus_index(tmp_path: Path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    output = tmp_path / "corpus"
    catalog_path.write_text(
        UrlCatalog(
            entry_url="https://docs.example.com/intro",
            nodes=[CatalogNode(url="https://docs.example.com/a", title="A")],
        ).model_dump_json(),
        encoding="utf-8",
    )
    calls: list[str] = []

    def fake_cache(catalog, output_dir, **_kwargs):
        calls.append(catalog.entry_url)
        assert output_dir == output
        return UrlCorpus(
            entry_url=catalog.entry_url,
            pages=[CorpusPage(url="https://docs.example.com/a", status="fetched", title="A")],
        )

    monkeypatch.setattr("loop_apidoc.url_corpus.cache_catalog_pages", fake_cache)

    result = runner.invoke(
        app,
        ["cache-url-pages", "--catalog", str(catalog_path), "--output", str(output)],
    )

    assert result.exit_code == 0, result.stdout
    assert calls == ["https://docs.example.com/intro"]
    assert json.loads((output / "corpus.json").read_text(encoding="utf-8"))["pages"][0]["title"] == "A"


def test_related_url_pages_writes_compact_candidate_cards(tmp_path: Path):
    corpus_path = tmp_path / "corpus.json"
    output = tmp_path / "related.json"
    corpus_path.write_text(
        UrlCorpus(
            entry_url="https://docs.example.com/intro",
            pages=[
                CorpusPage(
                    url="https://docs.example.com/a", status="fetched",
                    internal_links=["https://docs.example.com/errors"],
                ),
                CorpusPage(url="https://docs.example.com/errors", status="fetched", title="Errors"),
            ],
        ).model_dump_json(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["related-url-pages", "--corpus", str(corpus_path), "--url", "https://docs.example.com/a", "--output", str(output)],
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(output.read_text(encoding="utf-8")) == [
        {
            "url": "https://docs.example.com/errors",
            "title": "Errors",
            "headings": [],
            "breadcrumb": [],
            "body_file": None,
            "score": 100,
            "reasons": ["outbound_link"],
        }
    ]


def test_cache_url_entry_is_supported_without_a_catalog(tmp_path: Path, monkeypatch):
    output = tmp_path / "corpus"
    calls: list[tuple[str, int]] = []

    def fake_cache(catalog, output_dir, **kwargs):
        calls.append((catalog.entry_url, len(catalog.nodes)))
        return UrlCorpus(entry_url=catalog.entry_url, pages=[CorpusPage(url=catalog.entry_url, status="fetched")])

    monkeypatch.setattr("loop_apidoc.url_corpus.cache_catalog_pages", fake_cache)
    result = runner.invoke(app, ["cache-url-entry", "--url", "https://docs.example.com/intro", "--output", str(output)])

    assert result.exit_code == 0, result.stdout
    assert calls == [("https://docs.example.com/intro", 1)]
    assert json.loads((output / "corpus.json").read_text(encoding="utf-8"))["pages"][0]["url"] == "https://docs.example.com/intro"


def test_cache_catalog_fetches_one_document_for_multiple_anchor_sections(tmp_path: Path):
    import httpx

    from loop_apidoc.url_corpus import cache_catalog_pages

    catalog = UrlCatalog(
        entry_url="https://docs.example.com/transfer",
        nodes=[
            CatalogNode(url="https://docs.example.com/transfer", title="API", anchor="api"),
            CatalogNode(url="https://docs.example.com/transfer", title="Errors", anchor="errors"),
        ],
    )
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, text="<main><h1>Transfer</h1></main>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        corpus = cache_catalog_pages(catalog, tmp_path, client=client)

    assert requests == ["https://docs.example.com/transfer"]
    assert len(corpus.pages) == 1
    assert [section.anchor for section in corpus.pages[0].sections] == ["api", "errors"]
