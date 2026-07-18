"""Build a compact navigation catalog before fetching documentation pages.

The catalog is deliberately derived from a single entry page.  It records every
navigation target for coverage, but it never follows those links; a separate,
explicit selection decides what may be fetched later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, Field

from loop_apidoc.url_adapters import resolve_fetch_url


class CatalogNode(BaseModel):
    url: str
    title: str
    breadcrumb: list[str] = Field(default_factory=list)
    parent_url: str | None = None
    # A fragment identifies a section of a one-page document.  It is kept
    # separately because the fetch/corpus identity is the document URL (without
    # the fragment), while selection and coverage still need to see every
    # documented section.
    anchor: str | None = None


class UrlCatalog(BaseModel):
    entry_url: str
    nodes: list[CatalogNode] = Field(default_factory=list)


class UrlSelection(BaseModel):
    entry_url: str
    selected: list[CatalogNode] = Field(default_factory=list)
    unselected_count: int


class CatalogFetchError(RuntimeError):
    """The entry page could not be read as bounded HTML evidence."""


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str]
    children: list["_Element | str"] = field(default_factory=list)


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Element("document", {})
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Element(tag.lower(), {key.lower(): value or "" for key, value in attrs})
        self._stack[-1].children.append(node)
        if tag.lower() not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == normalized:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(data)


def _walk(element: _Element) -> Iterable[_Element]:
    yield element
    for child in element.children:
        if isinstance(child, _Element):
            yield from _walk(child)


def _text(element: _Element, *, exclude_lists: bool = False) -> str:
    parts: list[str] = []

    def visit(node: _Element | str) -> None:
        if isinstance(node, str):
            parts.append(node)
            return
        if exclude_lists and node.tag in {"ul", "ol"}:
            return
        for item in node.children:
            visit(item)

    visit(element)
    return " ".join("".join(parts).split())


def _navigation_roots(root: _Element) -> list[_Element]:
    elements = list(_walk(root))

    def has_list(element: _Element) -> bool:
        return any(node.tag in {"ul", "ol"} for node in _walk(element))

    sidebars = [
        element
        for element in elements
        if has_list(element)
        and (
            element.tag == "aside"
            or "sidebar" in element.attrs.get("class", "").casefold()
        )
    ]
    if sidebars:
        return sidebars

    navs = [element for element in elements if element.tag == "nav" and has_list(element)]
    if navs:
        return navs

    return [
        element
        for element in elements
        if has_list(element)
        and any(
            marker in element.attrs.get("class", "").casefold()
            for marker in ("menu", "navigation", "nav", "toc")
        )
    ]


def _direct_list_items(list_element: _Element) -> list[_Element]:
    return [child for child in list_element.children if isinstance(child, _Element) and child.tag == "li"]


# 純 UI 控制項（收合、分享、下拉）也是側欄的 <a>，但沒有文件目標；
# 讓它們成為 catalog 節點會把 UI 標籤當成待擷取的來源頁。
_UI_CONTROL_ATTRS = ("data-toggle", "data-bs-toggle", "aria-haspopup")


def _is_ui_control(anchor: _Element) -> bool:
    href = anchor.attrs.get("href", "").strip()
    if href in {"", "#"}:
        return True
    if anchor.attrs.get("role", "").casefold() == "button":
        return True
    return any(attr in anchor.attrs for attr in _UI_CONTROL_ATTRS)


def _first_anchor(element: _Element) -> _Element | None:
    def visit(node: _Element) -> _Element | None:
        if node.tag in {"ul", "ol"}:
            return None
        if node.tag == "a" and node.attrs.get("href") and not _is_ui_control(node):
            return node
        for child in node.children:
            if isinstance(child, _Element):
                found = visit(child)
                if found is not None:
                    return found
        return None

    return visit(element)


def _child_lists(element: _Element) -> list[_Element]:
    found: list[_Element] = []

    def visit(node: _Element) -> None:
        for child in node.children:
            if not isinstance(child, _Element):
                continue
            if child.tag in {"ul", "ol"}:
                found.append(child)
            elif child.tag != "li":
                visit(child)

    visit(element)
    return found


def _top_level_lists(element: _Element) -> list[_Element]:
    """Return lists not nested inside another list in one navigation root."""
    if element.tag in {"ul", "ol"}:
        return [element]
    found: list[_Element] = []

    def visit(node: _Element) -> None:
        for child in node.children:
            if not isinstance(child, _Element):
                continue
            if child.tag in {"ul", "ol"}:
                found.append(child)
            else:
                visit(child)

    visit(element)
    return found


def _canonical_url(entry_url: str, href: str) -> str | None:
    resolved = urlsplit(urljoin(entry_url, href))
    entry = urlsplit(entry_url)
    if resolved.scheme not in {"http", "https"} or resolved.netloc != entry.netloc:
        return None
    path = resolved.path.rstrip("/") or "/"
    return urlunsplit((resolved.scheme, resolved.netloc, path, resolved.query, ""))


def _canonical_navigation_url(entry_url: str, href: str) -> tuple[str, str | None] | None:
    """Return a same-origin navigation target and, when present, its fragment.

    Ordinary corpus links intentionally discard fragments, but sidebar anchors
    are meaningful coverage units in static single-page documentation.
    """
    canonical = _canonical_url(entry_url, href)
    if canonical is None:
        return None
    # Only fragments on the entry document denote sections that we can expose
    # without fetching another page.  A fragment on a child URL remains a
    # normal child-page link, preserving historic URL de-duplication semantics.
    entry = _canonical_url(entry_url, entry_url)
    fragment = urlsplit(urljoin(entry_url, href)).fragment if canonical == entry else None
    fragment = fragment or None
    return canonical, fragment


def build_catalog(entry_url: str, html: str) -> UrlCatalog:
    """Parse navigation only; no page links are fetched or otherwise followed."""
    parser = _TreeParser()
    parser.feed(html)
    parser.close()

    nodes: list[CatalogNode] = []
    seen: set[tuple[str, str | None]] = set()

    def visit_list(list_element: _Element, breadcrumb: list[str], parent_url: str | None) -> None:
        for item in _direct_list_items(list_element):
            anchor = _first_anchor(item)
            title = _text(anchor) if anchor is not None else _text(item, exclude_lists=True)
            title = title or "Untitled"
            node_breadcrumb = [*breadcrumb, title]
            child_parent = parent_url

            if anchor is not None:
                navigation_target = _canonical_navigation_url(entry_url, anchor.attrs["href"])
                if navigation_target is not None:
                    canonical, fragment = navigation_target
                    identity = (canonical, fragment)
                    if identity not in seen:
                        nodes.append(
                            CatalogNode(
                                url=canonical,
                                title=title,
                                breadcrumb=node_breadcrumb,
                                parent_url=parent_url,
                                anchor=fragment,
                            )
                        )
                        seen.add(identity)
                    child_parent = canonical

            for child_list in _child_lists(item):
                visit_list(child_list, node_breadcrumb, child_parent)

    for root in _navigation_roots(parser.root):
        for list_element in _top_level_lists(root):
            visit_list(list_element, [], None)

    return UrlCatalog(entry_url=_canonical_url(entry_url, entry_url) or entry_url, nodes=nodes)


def build_document_catalog(entry_url: str, markdown: str) -> UrlCatalog:
    """A raw Markdown source has no navigation; it is its own single catalog node."""
    canonical = _canonical_url(entry_url, entry_url) or entry_url
    title = next(
        (line.lstrip("#").strip() for line in markdown.splitlines() if line.startswith("# ")),
        None,
    )
    return UrlCatalog(
        entry_url=canonical,
        nodes=[CatalogNode(url=canonical, title=title or "Entry document")],
    )


def fetch_catalog(
    entry_url: str,
    *,
    client: httpx.Client | None = None,
    max_bytes: int = 5 * 1024 * 1024,
) -> UrlCatalog:
    """Fetch one bounded entry page and turn only its navigation into a catalog."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    target = resolve_fetch_url(entry_url)
    own_client = client is None
    active_client = client or httpx.Client(timeout=20, follow_redirects=True, trust_env=False)
    try:
        with active_client.stream("GET", target.url, headers={"Accept": target.accept}) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise CatalogFetchError(f"entry page exceeds {max_bytes} byte cap")
                chunks.append(chunk)
            encoding = response.encoding or "utf-8"
            text = b"".join(chunks).decode(encoding, errors="replace")
            if target.representation == "markdown":
                return build_document_catalog(entry_url, text)
            return build_catalog(str(response.url), text)
    except httpx.HTTPError as exc:
        raise CatalogFetchError(f"cannot fetch entry page: {exc.__class__.__name__}") from exc
    finally:
        if own_client:
            active_client.close()


def _matches(node: CatalogNode, values: Iterable[str]) -> bool:
    needle_values = [value.casefold().strip() for value in values if value.strip()]
    if not needle_values:
        return True
    haystack = " ".join([node.title, *node.breadcrumb, node.url]).casefold()
    return any(value in haystack for value in needle_values)


def select_catalog(
    catalog: UrlCatalog,
    *,
    branches: Iterable[str] = (),
    terms: Iterable[str] = (),
    urls: Iterable[str] = (),
) -> UrlSelection:
    """Select known nodes without widening the catalog or triggering a fetch."""
    branch_values = tuple(branches)
    term_values = tuple(terms)
    requested_urls = {
        _canonical_navigation_url(catalog.entry_url, url) or (url, None)
        for url in urls
    }
    has_keywords = any(value.strip() for value in (*branch_values, *term_values))
    if not has_keywords and not requested_urls:
        raise ValueError("at least one branch, term, or URL is required")

    # 沒有關鍵字時 `_matches` 對任何節點都成立，所以只給 URL 的選取必須是純 URL 比對，
    # 否則明確指定來源反而會選到整份 catalog。
    selected = [
        node
        for node in catalog.nodes
        if (node.url, node.anchor) in requested_urls
        or (has_keywords and _matches(node, branch_values) and _matches(node, term_values))
    ]
    return UrlSelection(
        entry_url=catalog.entry_url,
        selected=selected,
        unselected_count=len(catalog.nodes) - len(selected),
    )
