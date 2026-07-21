"""Deterministic acquisition helpers for GitBook-style ``llms.txt`` indexes."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx

from loop_apidoc.preparation.coverage import (
    CoverageExpected,
    CoverageResult,
    ExpectedSource,
    FetchMethod,
    ResultStatus,
    UrlCoverage,
)

class GitBookLlmsError(ValueError):
    """Raised when an LLMS index or its entry URL is unsafe to cache."""


@dataclass(frozen=True)
class GitBookPage:
    """One eligible Markdown page and its safe path below the sources root."""

    url: str
    destination: PurePosixPath


@dataclass(frozen=True)
class GitBookIndex:
    """The normalized index and its eligible, first-seen Markdown pages."""

    entry_url: str
    index_url: str
    pages: tuple[GitBookPage, ...]
    rejected_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class GitBookCacheResult:
    """Summary of a completed LLMS cache operation."""

    index_url: str
    sources: Path
    coverage_path: Path
    fetched: int
    failed: int


_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\((?P<url>[^)\s]+)(?:\s+[^)]*)?\)")
_HTTP_URL = re.compile(r"https?://[^\s<>\]\[\"']+", flags=re.IGNORECASE)


def parse_llms_index(entry_url: str, text: str) -> GitBookIndex:
    """Parse an LLMS index conservatively without following any link."""
    normalized_entry = normalize_entry_url(entry_url)
    index_url = f"{normalized_entry}llms.txt"
    accepted: list[GitBookPage] = []
    rejected: list[str] = []
    seen: set[str] = set()
    destinations: set[PurePosixPath] = set()

    for candidate in _candidate_urls(text):
        page = _eligible_page(normalized_entry, candidate)
        if page is None:
            rejected.append(candidate)
            continue
        if page.url in seen or page.destination in destinations:
            continue
        seen.add(page.url)
        destinations.add(page.destination)
        accepted.append(page)

    if not accepted:
        raise GitBookLlmsError("llms.txt contains no eligible same-origin Markdown URLs")
    return GitBookIndex(
        entry_url=normalized_entry,
        index_url=index_url,
        pages=tuple(accepted),
        rejected_urls=tuple(rejected),
    )


def cache_gitbook_llms(
    entry_url: str,
    *,
    sources: Path,
    coverage_output: Path,
    client: httpx.Client | None = None,
    max_bytes: int = 5 * 1024 * 1024,
) -> GitBookCacheResult:
    """Cache one GitBook LLMS index and every eligible Markdown source.

    Index validation and destination collision checks happen before page writes.
    A page fetch failure is retained in the coverage ledger and does not stop
    other eligible pages from becoming immutable local sources.
    """
    if max_bytes < 1:
        raise GitBookLlmsError("max_bytes must be positive")
    own_client = client is None
    active_client = client or httpx.Client(timeout=20, follow_redirects=True, trust_env=False)
    try:
        normalized_entry = normalize_entry_url(entry_url)
        index_url = f"{normalized_entry}llms.txt"
        index_text = _fetch_markdown(active_client, index_url, max_bytes=max_bytes).decode("utf-8")
        index = parse_llms_index(normalized_entry, index_text)
        _preflight_outputs(index, sources=sources, coverage_output=coverage_output)

        expected = [
            CoverageExpected(url=page.url, title=page.destination.as_posix(), source=ExpectedSource.USER)
            for page in index.pages
        ]
        results: list[CoverageResult] = []
        sources.mkdir(parents=True, exist_ok=True)
        for page in index.pages:
            destination = sources / page.destination
            try:
                raw = _fetch_markdown(active_client, page.url, max_bytes=max_bytes)
                raw.decode("utf-8")
            except (httpx.HTTPError, UnicodeDecodeError, ValueError) as exc:
                results.append(
                    CoverageResult(
                        url=page.url,
                        status=ResultStatus.FETCH_FAILED,
                        method=FetchMethod.DIRECT,
                        note=exc.__class__.__name__,
                    )
                )
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            _write_sidecar(destination, page.url, raw)
            results.append(
                CoverageResult(
                    url=page.url,
                    status=ResultStatus.FETCHED,
                    file=page.destination.as_posix(),
                    method=FetchMethod.DIRECT,
                )
            )

        coverage_output.parent.mkdir(parents=True, exist_ok=True)
        coverage_output.write_text(
            UrlCoverage(
                entry_url=index.entry_url,
                expected=expected,
                results=results,
            ).model_dump_json(indent=2, exclude_none=True),
            encoding="utf-8",
        )
        fetched = sum(result.status is ResultStatus.FETCHED for result in results)
        return GitBookCacheResult(
            index_url=index.index_url,
            sources=sources,
            coverage_path=coverage_output,
            fetched=fetched,
            failed=len(results) - fetched,
        )
    except (httpx.HTTPError, UnicodeDecodeError) as exc:
        raise GitBookLlmsError(f"cannot fetch llms.txt: {exc.__class__.__name__}") from exc
    finally:
        if own_client:
            active_client.close()


def normalize_entry_url(url: str) -> str:
    """Return an HTTP(S) entry URL with a canonical directory path."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise GitBookLlmsError("entry URL must be an absolute HTTP(S) URL")
    if parts.username or parts.password:
        raise GitBookLlmsError("entry URL must not contain credentials")
    path = parts.path or "/"
    if _has_unsafe_segments(path):
        raise GitBookLlmsError("entry URL path contains an unsafe segment")
    if not path.endswith("/"):
        path = f"{path}/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def _candidate_urls(text: str) -> list[str]:
    """Return link targets/bare URLs in first textual occurrence order."""
    candidates: list[tuple[int, str]] = []
    covered: list[tuple[int, int]] = []
    for match in _MARKDOWN_LINK.finditer(text):
        candidates.append((match.start("url"), match.group("url")))
        covered.append(match.span("url"))
    for match in _HTTP_URL.finditer(text):
        if any(start <= match.start() < end for start, end in covered):
            continue
        candidates.append((match.start(), match.group(0).rstrip(".,;:!")))
    return [value for _, value in sorted(candidates, key=lambda item: item[0])]


def _eligible_page(entry_url: str, candidate: str) -> GitBookPage | None:
    parts = urlsplit(candidate)
    entry = urlsplit(entry_url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return None
    if parts.username or parts.password or parts.netloc.lower() != entry.netloc.lower():
        return None
    if _has_unsafe_segments(parts.path):
        return None
    clean_path = parts.path
    if not clean_path.lower().endswith(".md"):
        return None
    if not clean_path.startswith(entry.path):
        return None
    relative = clean_path.removeprefix(entry.path)
    destination = _safe_destination(relative)
    if destination is None:
        return None
    url = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), clean_path, parts.query, ""))
    return GitBookPage(url=url, destination=destination)


def _has_unsafe_segments(path: str) -> bool:
    return any(
        decoded in {"", ".", ".."} or "\\" in decoded
        for segment in path.split("/")
        if segment
        if (decoded := unquote(segment)) is not None
    )


def _safe_destination(relative_path: str) -> PurePosixPath | None:
    if not relative_path or _has_unsafe_segments(relative_path):
        return None
    path = PurePosixPath(relative_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


def _fetch_markdown(client: httpx.Client, url: str, *, max_bytes: int) -> bytes:
    with client.stream("GET", url, headers={"Accept": "text/markdown,text/plain;q=0.9"}) as response:
        response.raise_for_status()
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise GitBookLlmsError(f"response exceeds {max_bytes} byte cap")
            chunks.append(chunk)
    return b"".join(chunks)


def _preflight_outputs(index: GitBookIndex, *, sources: Path, coverage_output: Path) -> None:
    if sources.exists() and not sources.is_dir():
        raise GitBookLlmsError(f"sources path is not a directory: {sources}")
    if coverage_output.exists():
        raise GitBookLlmsError(f"coverage output already exists: {coverage_output}")
    try:
        if coverage_output.resolve().is_relative_to(sources.resolve()):
            raise GitBookLlmsError("coverage output must not be inside sources")
    except OSError as exc:
        raise GitBookLlmsError(f"cannot validate output paths: {exc}") from exc
    collisions = [
        path
        for page in index.pages
        for path in (sources / page.destination, sources / f"{page.destination}.source.json")
        if path.exists()
    ]
    if collisions:
        raise GitBookLlmsError(f"immutable source output already exists: {collisions[0]}")


def _write_sidecar(destination: Path, url: str, raw: bytes) -> None:
    payload = {
        "url": url,
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "fetched_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    sidecar = destination.with_name(f"{destination.name}.source.json")
    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
