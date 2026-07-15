from __future__ import annotations

import pytest
import httpx

from loop_apidoc.url_catalog import build_catalog, fetch_catalog, select_catalog


_ENTRY_URL = "https://docs.example.com/cn/transfer/introduction"
_HTML = """
<html><body>
  <nav class="sidebar">
    <ul>
      <li><a href="/cn/transfer/introduction">Transfer wallet</a>
        <ul>
          <li><a href="/cn/transfer/login">Player login</a></li>
          <li><a href="/cn/transfer/cash">Cash transfer</a></li>
        </ul>
      </li>
      <li><a href="/cn/single/introduction">Single wallet</a></li>
      <li><a href="/cn/transfer/cash#duplicate">Cash transfer duplicate</a></li>
    </ul>
  </nav>
  <main><a href="/unrelated">This is not navigation</a></main>
</body></html>
"""


def test_build_catalog_reads_only_navigation_and_deduplicates_canonical_urls():
    catalog = build_catalog(_ENTRY_URL, _HTML)

    assert [node.url for node in catalog.nodes] == [
        "https://docs.example.com/cn/transfer/introduction",
        "https://docs.example.com/cn/transfer/login",
        "https://docs.example.com/cn/transfer/cash",
        "https://docs.example.com/cn/single/introduction",
    ]
    login = catalog.nodes[1]
    assert login.breadcrumb == ["Transfer wallet", "Player login"]
    assert login.parent_url == "https://docs.example.com/cn/transfer/introduction"
    assert all(node.url != "https://docs.example.com/unrelated" for node in catalog.nodes)


def test_select_catalog_intersects_branch_and_term_without_selecting_other_branches():
    catalog = build_catalog(_ENTRY_URL, _HTML)

    selection = select_catalog(catalog, branches=["transfer wallet"], terms=["cash"])

    assert [node.url for node in selection.selected] == [
        "https://docs.example.com/cn/transfer/cash"
    ]
    assert selection.unselected_count == 3


def test_select_catalog_rejects_an_unscoped_selection():
    catalog = build_catalog(_ENTRY_URL, _HTML)

    with pytest.raises(ValueError, match="at least one"):
        select_catalog(catalog)


def test_build_catalog_keeps_each_top_level_navigation_list():
    catalog = build_catalog(
        _ENTRY_URL,
        """
        <nav>
          <ul><li><a href="/cn/transfer/login">Login</a></li></ul>
          <ul><li><a href="/cn/transfer/cash">Cash</a></li></ul>
        </nav>
        """,
    )

    assert [node.title for node in catalog.nodes] == ["Login", "Cash"]


def test_build_catalog_prefers_sidebar_tree_over_header_navigation_links():
    catalog = build_catalog(
        _ENTRY_URL,
        """
        <header><nav><a href="/cn">Home</a></nav></header>
        <aside class="sidebar"><ul>
          <li><a href="/cn/transfer/introduction">Transfer</a></li>
          <li><a href="/cn/single/introduction">Single</a></li>
        </ul></aside>
        """,
    )

    assert [node.title for node in catalog.nodes] == ["Transfer", "Single"]


def test_fetch_catalog_downloads_only_the_entry_page():
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, text=_HTML)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        catalog = fetch_catalog(_ENTRY_URL, client=client)

    assert requested == [_ENTRY_URL]
    assert len(catalog.nodes) == 4
