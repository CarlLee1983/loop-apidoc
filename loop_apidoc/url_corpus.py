"""Local, deterministic metadata for a cached documentation corpus."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from loop_apidoc.url_catalog import _Element, _TreeParser, _canonical_url, _walk, UrlCatalog


class PageSection(BaseModel):
    anchor: str
    title: str
    breadcrumb: list[str] = Field(default_factory=list)


class PageMetadata(BaseModel):
    url: str
    title: str | None = None
    headings: list[str] = Field(default_factory=list)
    body_text: str
    internal_links: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class CorpusPage(BaseModel):
    url: str
    status: Literal["fetched", "fetch_failed"]
    raw_file: str | None = None
    body_file: str | None = None
    content_sha256: str | None = None
    byte_size: int = 0
    title: str | None = None
    headings: list[str] = Field(default_factory=list)
    breadcrumb: list[str] = Field(default_factory=list)
    internal_links: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    sections: list[PageSection] = Field(default_factory=list)
    body_characters: int = 0
    note: str | None = None


class UrlCorpus(BaseModel):
    schema_version: str = "1.0"
    entry_url: str
    pages: list[CorpusPage] = Field(default_factory=list)


class RelatedPage(BaseModel):
    url: str
    title: str | None = None
    headings: list[str] = Field(default_factory=list)
    breadcrumb: list[str] = Field(default_factory=list)
    body_file: str | None = None
    score: int
    reasons: list[str] = Field(default_factory=list)


def _content_text(element: _Element) -> str:
    parts: list[str] = []

    def visit(node: _Element | str) -> None:
        if isinstance(node, str):
            parts.append(node)
            return
        if node.tag in {"aside", "footer", "nav", "script", "style", "template"}:
            return
        for child in node.children:
            visit(child)

    visit(element)
    return " ".join(" ".join(parts).split())


def _first_text(elements: list[_Element]) -> str | None:
    for element in elements:
        text = _content_text(element)
        if text:
            return text
    return None


def _entities(text: str) -> list[str]:
    matches: list[tuple[int, str]] = []
    for match in re.finditer(r"\baction\s*(\d+)\b", text, flags=re.IGNORECASE):
        matches.append((match.start(), f"action:{match.group(1)}"))
    for match in re.finditer(r"\b([1-9]\d{3,4})\b", text):
        matches.append((match.start(), f"error:{match.group(1)}"))
    return list(dict.fromkeys(value for _, value in sorted(matches)))


def extract_page_metadata(url: str, html: str) -> PageMetadata:
    """Extract a compact page card from ``main`` without returning site chrome."""
    parser = _TreeParser()
    parser.feed(html)
    parser.close()
    elements = list(_walk(parser.root))
    main = next((element for element in elements if element.tag == "main"), parser.root)
    headings = [
        text
        for element in _walk(main)
        if element.tag in {"h1", "h2", "h3", "h4"}
        if (text := _content_text(element))
    ]
    title = _first_text([element for element in _walk(main) if element.tag == "h1"])
    if title is None:
        title = _first_text([element for element in elements if element.tag == "title"])

    links: list[str] = []
    seen: set[str] = set()
    for element in _walk(main):
        if element.tag != "a" or not element.attrs.get("href"):
            continue
        resolved = _canonical_url(url, element.attrs["href"])
        if resolved is not None and resolved not in seen:
            links.append(resolved)
            seen.add(resolved)

    body_text = _content_text(main)
    return PageMetadata(
        url=url,
        title=title,
        headings=headings,
        body_text=body_text,
        internal_links=links,
        entities=_entities(body_text),
    )


def cache_catalog_pages(
    catalog: UrlCatalog,
    output_dir: Path,
    *,
    client: httpx.Client | None = None,
    max_pages: int = 200,
    max_bytes_per_page: int = 5 * 1024 * 1024,
) -> UrlCorpus:
    """Cache every catalog node as local evidence without involving a model."""
    if max_pages < 1 or max_bytes_per_page < 1:
        raise ValueError("max_pages and max_bytes_per_page must be positive")
    if len(catalog.nodes) > max_pages:
        raise ValueError(f"catalog has {len(catalog.nodes)} pages, above max_pages={max_pages}")

    raw_dir = output_dir / "raw"
    body_dir = output_dir / "body"
    raw_dir.mkdir(parents=True, exist_ok=True)
    body_dir.mkdir(parents=True, exist_ok=True)

    own_client = client is None
    active_client = client or httpx.Client(timeout=20, follow_redirects=True, trust_env=False)
    pages: list[CorpusPage] = []
    try:
        # Several sidebar anchors can identify sections in one static document.
        # Fetch that document once, but retain all anchors as local section
        # metadata so selection and later model reading stay precise.
        nodes_by_url: dict[str, list] = {}
        for node in catalog.nodes:
            nodes_by_url.setdefault(node.url, []).append(node)
        for url, nodes in nodes_by_url.items():
            node = nodes[0]
            try:
                with active_client.stream("GET", url, headers={"Accept": "text/html"}) as response:
                    response.raise_for_status()
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes_per_page:
                            raise ValueError(f"response exceeds {max_bytes_per_page} byte cap")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    html = raw.decode(response.encoding or "utf-8", errors="replace")
            except (httpx.HTTPError, ValueError) as exc:
                pages.append(CorpusPage(url=url, status="fetch_failed", note=exc.__class__.__name__))
                continue

            digest = hashlib.sha256(raw).hexdigest()
            raw_relative = Path("raw") / f"{digest}.html"
            body_relative = Path("body") / f"{digest}.txt"
            raw_path = output_dir / raw_relative
            if not raw_path.exists():
                raw_path.write_bytes(raw)

            metadata = extract_page_metadata(url, html)
            body_path = output_dir / body_relative
            if not body_path.exists():
                body_path.write_text(metadata.body_text, encoding="utf-8")
            pages.append(
                CorpusPage(
                    url=url,
                    status="fetched",
                    raw_file=raw_relative.as_posix(),
                    body_file=body_relative.as_posix(),
                    content_sha256=digest,
                    byte_size=len(raw),
                    title=metadata.title or node.title,
                    headings=metadata.headings,
                    breadcrumb=node.breadcrumb,
                    internal_links=metadata.internal_links,
                    entities=metadata.entities,
                    sections=[
                        PageSection(anchor=item.anchor, title=item.title, breadcrumb=item.breadcrumb)
                        for item in nodes
                        if item.anchor is not None
                    ],
                    body_characters=len(metadata.body_text),
                )
            )
    finally:
        if own_client:
            active_client.close()

    return UrlCorpus(entry_url=catalog.entry_url, pages=pages)


def find_related_pages(
    corpus: UrlCorpus,
    url: str,
    *,
    limit: int = 20,
) -> list[RelatedPage]:
    """Return evidence-based candidate cards without loading corpus body text."""
    if limit < 1:
        raise ValueError("limit must be positive")
    target = next((page for page in corpus.pages if page.url == url), None)
    if target is None:
        raise ValueError(f"URL is not in corpus: {url}")

    related: list[RelatedPage] = []
    target_entities = set(target.entities)
    entity_frequency = Counter(
        entity
        for page in corpus.pages
        if page.status == "fetched"
        for entity in set(page.entities)
    )
    target_branch = target.breadcrumb[0].casefold() if target.breadcrumb else None
    for page in corpus.pages:
        if page.url == target.url or page.status != "fetched":
            continue
        score = 0
        reasons: list[str] = []
        if target_branch and page.breadcrumb and page.breadcrumb[0].casefold() == target_branch:
            score += 20
            reasons.append("same_branch")
        if page.url in target.internal_links:
            score += 100
            reasons.append("outbound_link")
        if target.url in page.internal_links:
            score += 80
            reasons.append("inbound_link")
        for entity in sorted(target_entities.intersection(page.entities)):
            score += max(5, 60 // entity_frequency[entity])
            reasons.append(f"shared_entity:{entity}")
        if score:
            related.append(
                RelatedPage(
                    url=page.url,
                    title=page.title,
                    headings=page.headings,
                    breadcrumb=page.breadcrumb,
                    body_file=page.body_file,
                    score=score,
                    reasons=reasons,
                )
            )
    return sorted(related, key=lambda page: (-page.score, page.url))[:limit]
