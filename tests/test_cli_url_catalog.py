from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.url_catalog import build_catalog


runner = CliRunner()


def _catalog():
    return build_catalog(
        "https://docs.example.com/transfer/introduction",
        """
        <nav><ul><li><a href="/transfer/introduction">Transfer</a><ul>
        <li><a href="/transfer/cash">Cash transfer</a></li>
        </ul></li><li><a href="/single/intro">Single wallet</a></li></ul></nav>
        """,
    )


def test_catalog_url_writes_a_navigation_catalog_without_fetching_child_pages(tmp_path: Path, monkeypatch):
    output = tmp_path / "catalog.json"
    calls: list[str] = []

    def fake_fetch(url: str, **_kwargs):
        calls.append(url)
        return _catalog()

    monkeypatch.setattr("loop_apidoc.url_catalog.fetch_catalog", fake_fetch)

    result = runner.invoke(
        app,
        ["catalog-url", "--url", "https://docs.example.com/transfer/introduction", "--output", str(output)],
    )

    assert result.exit_code == 0, result.stdout
    assert calls == ["https://docs.example.com/transfer/introduction"]
    assert [node["title"] for node in json.loads(output.read_text())["nodes"]] == [
        "Transfer", "Cash transfer", "Single wallet"
    ]


def test_select_url_writes_only_the_requested_scope(tmp_path: Path):
    catalog_path = tmp_path / "catalog.json"
    output = tmp_path / "selection.json"
    catalog_path.write_text(_catalog().model_dump_json(), encoding="utf-8")

    result = runner.invoke(
        app,
        ["select-url", "--catalog", str(catalog_path), "--branch", "transfer", "--term", "cash", "--output", str(output)],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert [node["url"] for node in payload["selected"]] == [
        "https://docs.example.com/transfer/cash"
    ]
    assert payload["unselected_count"] == 2


def test_catalog_keeps_static_single_page_anchors_as_distinct_sections():
    catalog = build_catalog(
        "https://docs.example.com/transfer/zh-tw/",
        '<aside class="sidebar"><ul><li><a href="#5-api-5-1">API 5.1</a></li><li><a href="#errors">Errors</a></li></ul></aside>',
    )

    assert [(node.url, node.anchor, node.title) for node in catalog.nodes] == [
        ("https://docs.example.com/transfer/zh-tw", "5-api-5-1", "API 5.1"),
        ("https://docs.example.com/transfer/zh-tw", "errors", "Errors"),
    ]


def test_select_url_can_select_one_static_page_anchor(tmp_path: Path):
    catalog = build_catalog(
        "https://docs.example.com/transfer/zh-tw/",
        '<nav><ul><li><a href="#api">API</a></li></ul></nav>',
    )
    catalog_path = tmp_path / "catalog.json"
    output = tmp_path / "selection.json"
    catalog_path.write_text(catalog.model_dump_json(), encoding="utf-8")

    result = runner.invoke(app, ["select-url", "--catalog", str(catalog_path), "--url", "#api", "--output", str(output)])

    assert result.exit_code == 0, result.stdout
    assert json.loads(output.read_text(encoding="utf-8"))["selected"][0]["anchor"] == "api"


def test_catalog_recognizes_static_toc_list_without_nav_or_sidebar():
    catalog = build_catalog(
        "https://docs.example.com/transfer/",
        '<ul id="toc" class="toc-list-h1"><li><a href="#api">API</a></li></ul>',
    )

    assert [(node.title, node.anchor) for node in catalog.nodes] == [("API", "api")]
