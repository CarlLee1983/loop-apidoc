from __future__ import annotations

import json
from pathlib import Path

import httpx
from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.url_catalog import CatalogNode, UrlCatalog
from loop_apidoc.url_corpus import (
    CorpusPage,
    UrlCorpus,
    cache_catalog_pages,
    is_spa_shell,
    openapi_spec_candidates,
    recognized_spec_kind,
)


runner = CliRunner()


def test_openapi_spec_candidates_use_only_the_page_origin():
    assert openapi_spec_candidates("https://docs.example.com/guides/intro?lang=en") == [
        "https://docs.example.com/swagger.json",
        "https://docs.example.com/openapi.json",
        "https://docs.example.com/v3/api-docs",
        "https://docs.example.com/api-doc/v3/sections",
    ]


def test_recognized_spec_kind_requires_an_openapi_or_swagger_root_field():
    assert recognized_spec_kind(b'{"openapi":"3.1.0"}', "utf-8") == "openapi"
    assert recognized_spec_kind(b'{"swagger":"2.0"}', "utf-8") == "swagger"
    assert recognized_spec_kind(b'{"status":"ok"}', "utf-8") is None
    assert recognized_spec_kind(b"not json", "utf-8") is None


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


def test_cache_url_pages_warns_on_detected_spa_shell(tmp_path: Path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        UrlCatalog(
            entry_url="https://docs.example.com/intro",
            nodes=[CatalogNode(url="https://docs.example.com/intro", title="Intro")],
        ).model_dump_json(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "loop_apidoc.url_corpus.cache_catalog_pages",
        lambda *_args, **_kwargs: UrlCorpus(
            entry_url="https://docs.example.com/intro",
            pages=[
                CorpusPage(
                    url="https://docs.example.com/intro",
                    status="fetched",
                    spa_shell_detected=True,
                ),
                CorpusPage(
                    url="https://docs.example.com/openapi.json",
                    status="fetched",
                    source_kind="openapi_spec",
                ),
            ],
        ),
    )

    result = runner.invoke(
        app,
        ["cache-url-pages", "--catalog", str(catalog_path), "--output", str(tmp_path / "out")],
    )

    assert result.exit_code == 0, result.stdout
    assert "1/1 pages look like un-rendered SPA shells" in result.stderr


def test_cache_url_pages_no_shell_emits_no_warning(tmp_path: Path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        UrlCatalog(
            entry_url="https://docs.example.com/intro",
            nodes=[CatalogNode(url="https://docs.example.com/intro", title="Intro")],
        ).model_dump_json(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "loop_apidoc.url_corpus.cache_catalog_pages",
        lambda *_args, **_kwargs: UrlCorpus(
            entry_url="https://docs.example.com/intro",
            pages=[CorpusPage(url="https://docs.example.com/intro", status="fetched")],
        ),
    )

    result = runner.invoke(
        app,
        ["cache-url-pages", "--catalog", str(catalog_path), "--output", str(tmp_path / "out")],
    )

    assert result.exit_code == 0, result.stdout
    assert "pages look like un-rendered SPA shells" not in result.stderr


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


def test_cache_url_entry_warns_on_detected_spa_shell(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "loop_apidoc.url_corpus.cache_catalog_pages",
        lambda *_args, **_kwargs: UrlCorpus(
            entry_url="https://docs.example.com/intro",
            pages=[
                CorpusPage(
                    url="https://docs.example.com/intro",
                    status="fetched",
                    spa_shell_detected=True,
                ),
                CorpusPage(
                    url="https://docs.example.com/openapi.json",
                    status="fetched",
                    source_kind="openapi_spec",
                ),
            ],
        ),
    )

    result = runner.invoke(
        app,
        ["cache-url-entry", "--url", "https://docs.example.com/intro", "--output", str(tmp_path / "out")],
    )

    assert result.exit_code == 0, result.stdout
    assert "1/1 pages look like un-rendered SPA shells" in result.stderr


def test_cache_url_entry_counts_only_fetched_document_sources(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "loop_apidoc.url_corpus.cache_catalog_pages",
        lambda *_args, **_kwargs: UrlCorpus(
            entry_url="https://docs.example.com/intro",
            pages=[
                CorpusPage(url="https://docs.example.com/intro", status="fetched"),
                CorpusPage(
                    url="https://docs.example.com/openapi.json",
                    status="fetched",
                    source_kind="openapi_spec",
                ),
            ],
        ),
    )

    result = runner.invoke(
        app,
        ["cache-url-entry", "--url", "https://docs.example.com/intro", "--output", str(tmp_path / "out")],
    )

    assert result.exit_code == 0, result.stdout
    assert "快取 1 / 1 個入口頁" in result.stdout


def test_cache_url_entry_no_shell_emits_no_warning(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "loop_apidoc.url_corpus.cache_catalog_pages",
        lambda *_args, **_kwargs: UrlCorpus(
            entry_url="https://docs.example.com/intro",
            pages=[CorpusPage(url="https://docs.example.com/intro", status="fetched")],
        ),
    )

    result = runner.invoke(
        app,
        ["cache-url-entry", "--url", "https://docs.example.com/intro", "--output", str(tmp_path / "out")],
    )

    assert result.exit_code == 0, result.stdout
    assert "pages look like un-rendered SPA shells" not in result.stderr


def test_cache_catalog_fetches_one_document_for_multiple_anchor_sections(tmp_path: Path):
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


# ── SPA shell 偵測 ─────────────────────────────────────────────────────

_SHELL_HTML = (
    "<html><body><noscript>We're sorry but this app doesn't work properly "
    "without JavaScript enabled. Please enable it to continue.</noscript>"
    "<div id='app'></div></body></html>"
)
_SHELL_BODY = (
    "We're sorry but this app doesn't work properly without JavaScript enabled."
)


def _fetch_one(html: str, tmp_path: Path):
    catalog = UrlCatalog(
        entry_url="https://docs.example.com/page",
        nodes=[CatalogNode(url="https://docs.example.com/page", title="Doc")],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return cache_catalog_pages(catalog, tmp_path, client=client)


def test_js_shell_body_is_detected_as_a_spa_shell():
    assert is_spa_shell(_SHELL_HTML, _SHELL_BODY) is True


def test_noscript_shell_without_a_known_phrase_is_detected():
    html = "<html><body><noscript>請開啟 JavaScript</noscript><div id=app></div></body></html>"

    assert is_spa_shell(html, "請開啟 JavaScript") is True


def test_long_page_mentioning_javascript_is_not_a_spa_shell():
    """真正渲染出來的文件頁提到 JavaScript 不等於 shell —— 分辨兩者的是 body 長度,
    不是關鍵字。少了長度上界,任何講 JS 的 API 文件都會被誤標並誤導 agent 去跑
    headless render。"""
    body = (
        "This endpoint returns a JSON body. Browser clients must enable JavaScript "
        "to use the interactive console shown below. " + "詳細參數說明如下。" * 60
    )
    html = f"<html><body><main>{body}</main></body></html>"

    assert len(body) >= 500
    assert is_spa_shell(html, body) is False


def test_spa_shell_page_carries_the_flag_and_a_remediation_note(tmp_path: Path):
    corpus = _fetch_one(_SHELL_HTML, tmp_path)

    assert len(corpus.pages) == 1
    assert corpus.pages[0].spa_shell_detected is True
    assert "SPA_SHELL_DETECTED" in (corpus.pages[0].note or "")


def test_spa_shell_caches_a_recognized_openapi_document_as_a_distinct_source(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/page":
            return httpx.Response(200, text=_SHELL_HTML)
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json={"openapi": "3.1.0"})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        corpus = cache_catalog_pages(
            UrlCatalog(
                entry_url="https://docs.example.com/page",
                nodes=[CatalogNode(url="https://docs.example.com/page", title="Doc")],
            ),
            tmp_path,
            client=client,
        )

    spec = next(page for page in corpus.pages if page.source_kind == "openapi_spec")
    assert spec.url == "https://docs.example.com/openapi.json"
    assert spec.discovered_from == ["https://docs.example.com/page"]
    assert spec.raw_file and spec.raw_file.endswith(".json")


def test_spa_shell_probe_rejects_redirected_openapi_candidates(tmp_path: Path):
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/page":
            return httpx.Response(200, text=_SHELL_HTML)
        if request.url.path == "/openapi.json":
            return httpx.Response(
                302,
                headers={"Location": "https://untrusted.example.com/api.json"},
            )
        if request.url.host == "untrusted.example.com":
            return httpx.Response(200, json={"openapi": "3.1.0"})
        return httpx.Response(404)

    with httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        corpus = cache_catalog_pages(
            UrlCatalog(
                entry_url="https://docs.example.com/page",
                nodes=[CatalogNode(url="https://docs.example.com/page", title="Doc")],
            ),
            tmp_path,
            client=client,
        )

    assert all(page.source_kind != "openapi_spec" for page in corpus.pages)
    assert requests == [
        "https://docs.example.com/page",
        "https://docs.example.com/swagger.json",
        "https://docs.example.com/openapi.json",
        "https://docs.example.com/v3/api-docs",
        "https://docs.example.com/api-doc/v3/sections",
    ]
    assert not list((tmp_path / "raw").glob("*.json"))


def test_spa_shell_probe_ignores_missing_and_non_spec_json(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/page":
            return httpx.Response(200, text=_SHELL_HTML)
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        corpus = cache_catalog_pages(
            UrlCatalog(
                entry_url="https://docs.example.com/page",
                nodes=[CatalogNode(url="https://docs.example.com/page", title="Doc")],
            ),
            tmp_path,
            client=client,
        )

    assert [page.url for page in corpus.pages] == ["https://docs.example.com/page"]


def test_spa_shell_probe_deduplicates_candidates_and_preserves_shell_order(tmp_path: Path):
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path in {"/one", "/two"}:
            return httpx.Response(200, text=_SHELL_HTML)
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json={"swagger": "2.0"})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        corpus = cache_catalog_pages(
            UrlCatalog(
                entry_url="https://docs.example.com/one",
                nodes=[
                    CatalogNode(url="https://docs.example.com/one", title="One"),
                    CatalogNode(url="https://docs.example.com/two", title="Two"),
                ],
            ),
            tmp_path,
            client=client,
        )

    spec = next(page for page in corpus.pages if page.source_kind == "openapi_spec")
    assert requests.count("https://docs.example.com/openapi.json") == 1
    assert spec.discovered_from == [
        "https://docs.example.com/one",
        "https://docs.example.com/two",
    ]


def test_rendered_page_is_not_flagged_and_keeps_note_empty(tmp_path: Path):
    html = (
        "<html><body><main><h1>Transfer API</h1><p>"
        + "回傳 JSON envelope,欄位說明如下。" * 40
        + "</p></main></body></html>"
    )

    corpus = _fetch_one(html, tmp_path)

    assert len(corpus.pages) == 1
    assert corpus.pages[0].spa_shell_detected is False
    assert corpus.pages[0].note is None
