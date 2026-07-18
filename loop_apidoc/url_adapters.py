"""Map a documentation URL to the canonical representation that carries its body.

Some hosts serve a JavaScript shell at the human-facing URL and keep the whole
document behind a separate raw endpoint.  Fetching the shell silently loses the
source, so the mapping is resolved deterministically before any request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

Representation = Literal["html", "markdown"]

_HTML_ACCEPT = "text/html"
_MARKDOWN_ACCEPT = "text/markdown, text/plain;q=0.9"

_HACKMD_HOSTS = {"hackmd.io", "www.hackmd.io"}
# HackMD 的應用路由與筆記 ID 共用同一層路徑，只有非路由的第一段才是筆記。
_HACKMD_RESERVED = {
    "",
    "api",
    "features",
    "help",
    "login",
    "logout",
    "new",
    "pricing",
    "s",
    "settings",
    "signup",
}


@dataclass(frozen=True)
class FetchTarget:
    """The URL to actually request, plus the representation it will return."""

    url: str
    representation: Representation
    accept: str


def _hackmd_download_url(parts) -> str | None:
    segments = [segment for segment in parts.path.split("/") if segment]
    if not segments or segments[0].casefold() in _HACKMD_RESERVED:
        return None
    if segments[-1] == "download":
        return urlunsplit((parts.scheme, parts.netloc, "/" + "/".join(segments), "", ""))
    return urlunsplit((parts.scheme, parts.netloc, "/" + "/".join([*segments, "download"]), "", ""))


def resolve_fetch_url(url: str) -> FetchTarget:
    """Return the fetchable URL and its representation; performs no I/O."""
    parts = urlsplit(url)
    if parts.netloc.casefold() in _HACKMD_HOSTS:
        download = _hackmd_download_url(parts)
        if download is not None:
            return FetchTarget(download, "markdown", _MARKDOWN_ACCEPT)
    return FetchTarget(url, "html", _HTML_ACCEPT)
