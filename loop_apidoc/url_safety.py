"""Egress policy for every outbound fetch (issue #155).

A URL entering this pipeline is operator-supplied, and on this project it
usually arrives from a supplier's portal rather than from the operator's own
typing. `inspect-source-risk` already treats fetched *content* as untrusted
before a model reads it; nothing gated the *acquisition*, so a URL could send
the fetcher at a cloud metadata endpoint or an internal service and the
response would be content-addressed into the corpus as a source.

**The criterion:** a URL may be fetched only when its scheme is HTTP(S), it
carries no userinfo, and *every* address it resolves to is globally routable,
non-multicast, and outside the address-translation ranges listed below. Every
address, not any: a name resolving to one public and one private address is the
standard bypass — validate the public one, connect to the private one.

"Globally routable" is `ipaddress.is_global` plus those exclusions, because
`is_global` alone answers a registry question rather than a reachability one.

This module performs DNS resolution and nothing else. It opens no socket and
writes no file, so it is testable without a network: the resolver is an
injected seam, and every test supplies its own.

Rebinding is deliberately out of scope. Between validation and connection a
name can be re-resolved to a different address; defeating that needs the
connection pinned to the address that was checked, which is a much more
invasive change to every call site. Validate-then-fetch closes the large
majority of the exposure, and pinning stays a separate decision.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import unquote, urlsplit

import httpx
from pydantic import PlainSerializer

from . import privacy

Resolver = Callable[[str, int], list[str]]

# Inside a unique-local / link-local range and so already refused by the
# `is_global` test. Named anyway, because these are the addresses an SSRF is
# usually aimed at and a reader should not have to derive that.
_METADATA_ENDPOINTS = frozenset({"169.254.169.254", "fd00:ec2::254"})

# `is_global` means "not flagged non-global in a special-purpose address
# registry", which is close to, but not the same as, "safe to connect to".
# These ranges are flagged global and are still not safe targets:
#
#   64:ff9b::/96   RFC 6052 NAT64. Its low 32 bits are an arbitrary IPv4, so an
#                  AAAA of `64:ff9b::a9fe:a9fe` reaches 169.254.169.254 through
#                  any NAT64 gateway — increasingly common on IPv6-only cloud
#                  subnets — while every check here reports "globally routable".
#   64:ff9b:1::/48 the local-use NAT64 prefix, same mechanism.
#   192.88.99.0/24 6to4 relay anycast: a relay, not an endpoint.
#
# Multicast is excluded separately below: `is_global` is True for 224.0.0.1 and
# ff02::1, and an HTTP fetch of a multicast group is never a supplier document.
_TRANSLATED_RANGES = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("64:ff9b::/96", "64:ff9b:1::/48", "192.88.99.0/24")
)

class UrlSafetyError(ValueError):
    """A URL that must not be fetched. Fail closed: callers do not proceed."""


@dataclass(frozen=True)
class UrlFetchPolicy:
    """The bounds an outbound fetch is held to, in one reviewable place."""

    version: int = 1
    timeout_seconds: float = 20.0
    max_redirects: int = 5


@dataclass(frozen=True)
class ValidatedTarget:
    """A URL that passed the criterion, plus what it resolved to. The addresses
    are carried so a caller that later pins the connection has them without a
    second, possibly different, resolution."""

    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


def _resolve(host: str, port: int) -> list[str]:
    # sockaddr[0] is the address for both AF_INET and AF_INET6; the typeshed
    # union covers the whole tuple, hence the explicit str().
    return list(
        dict.fromkeys(
            str(item[4][0])
            for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        )
    )


# `is_global` returned wrong answers for 0.0.0.0/8 and 100.64.0.0/10 before the
# CPython fixes in 3.11.9 / 3.12.4, both inside this project's declared support
# window. `tests/test_url_safety.py` parametrizes those ranges, so an interpreter
# below those patch levels fails the suite loudly instead of passing silently.
def _is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if not ip.is_global or ip.is_multicast:
        return False
    if str(ip) in _METADATA_ENDPOINTS:
        return False
    return not any(ip in network for network in _TRANSLATED_RANGES)


def validate_url(url: str, *, resolver: Resolver = _resolve) -> ValidatedTarget:
    """Refuse anything that is not a public HTTP(S) target, or raise."""
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise UrlSafetyError("only public HTTP(S) URLs may be fetched")
        if parsed.username is not None or parsed.password is not None:
            raise UrlSafetyError(
                "URL userinfo is forbidden: credentials would be written verbatim "
                "into corpus and provenance artifacts"
            )
        host = parsed.hostname
        if not host:
            raise UrlSafetyError("URL host is required")
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        if isinstance(exc, UrlSafetyError):
            raise
        raise UrlSafetyError(f"invalid URL: {exc}") from exc

    try:
        ipaddress.ip_address(host)
        addresses: tuple[str, ...] = (host,)
    except ValueError:
        try:
            addresses = tuple(resolver(host, port))
        except OSError as exc:
            # The resolver's own message can carry the queried name and the
            # configured search domains, and this text reaches logs and reports.
            raise UrlSafetyError(
                f"DNS resolution failed: {exc.__class__.__name__}"
            ) from exc

    if not addresses or any(not _is_public(address) for address in addresses):
        raise UrlSafetyError(f"URL resolves to a non-public address: {host}")
    return ValidatedTarget(url=url, host=host.lower(), port=port, addresses=addresses)


REDACTED = "[REDACTED]"

# Which *names* denote a credential is `privacy.py`'s question — AGENTS.md makes
# it the single owner of sensitive field detection, and a second vocabulary here
# would drift from it. What this module owns is the URL mechanics: where a name
# ends and a value begins, and how to put a replacement back without disturbing
# anything else.
_CREDENTIAL_SEGMENT = re.compile(
    rf"\A(?:{privacy.JWT_BODY}"
    # An AWS access key id: a fixed four-character type prefix plus 16
    # upper-alphanumeric. Only unambiguous formats are matched, never an entropy
    # or length heuristic — the path is where provenance is read, and a
    # heuristic eats a 40-hex digest, a version number and a long slug alike.
    r"|(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ABIA|ACCA)[0-9A-Z]{16}"
    r")\Z"
)

# `urlsplit` silently drops these, so a segment carrying one is not the segment
# that goes on the wire. They are stripped before the shape test and then vanish
# with the segment if it matches: a credential is no less one for having a
# newline glued to it.
_URL_STRIPPED = str.maketrans("", "", "\t\r\n")

# `;` stopped being a query separator for `parse_qsl` in 3.9.2, but generators
# and servers still emit it. Splitting on both and keeping the separator that
# was there is what lets the fail-safe reading coexist with byte-for-byte
# round-tripping of a query this never touches.
_QUERY_SEPARATOR = re.compile(r"([&;])")


def _redact_query(query: str) -> str:
    parts = _QUERY_SEPARATOR.split(query)
    for index in range(0, len(parts), 2):
        key, sep, _value = parts[index].partition("=")
        if sep and privacy.is_credential_key(unquote(key)):
            parts[index] = f"{key}={REDACTED}"
    return "".join(parts)


def _redact_path(path: str) -> str:
    return "/".join(
        REDACTED
        if _CREDENTIAL_SEGMENT.match(segment.translate(_URL_STRIPPED))
        else segment
        for segment in path.split("/")
    )


def _redact_fragment(fragment: str) -> str:
    """A fragment is either a SPA hash route — a path that happens to live after
    the `#`, so it can carry a segment-shaped credential — or a parameter list.
    The OAuth implicit and hybrid responses return their tokens as the second
    shape, `&`-joined with no `?` at all, and that is the likeliest way a
    credential ever reaches a fragment."""
    route, question, query = fragment.partition("?")
    if not question and "=" in route:
        return _redact_query(route)
    return f"{_redact_path(route)}{question}{_redact_query(query)}"


def _redact_userinfo(origin: str) -> str:
    """`scheme://user:pw@host` becomes `scheme://[REDACTED]@host`, username
    included: HTTP basic auth is a routine way to carry an API key, so the name
    half is not reliably a name. `validate_url` refuses userinfo outright, but
    not every command fetches — `normalize-html-snapshot` takes its `--url` as
    operator metadata and writes it to a sidecar without ever passing the gate —
    so the write side cannot lean on the read side's guarantee.
    """
    mark = origin.rfind("@")
    if mark == -1:
        return origin
    return f"{origin[:origin.find('//') + 2]}{REDACTED}{origin[mark:]}"


def _split_origin(before: str) -> tuple[str, str]:
    """`scheme://authority` and the path after it, cut from the original string.

    Deliberately not `urlsplit`: its `path` is a *normalized* view — control
    characters removed — so splicing by its length lands off by one on any URL
    that contains one, and its parser raises on a malformed authority, which in
    a serializer turns a bad input into a crashed write.
    """
    mark = before.find("//")
    if mark == -1 or not before[:mark].endswith(":"):
        return "", before
    slash = before.find("/", mark + 2)
    return (before, "") if slash == -1 else (before[:slash], before[slash:])


def redact_url(url: str) -> str:
    """Replace credential values in `url`, leaving every other byte as it was.

    Splices replacements into the original string rather than re-encoding it:
    `parse_qsl` + `urlencode` does not round-trip a real query string, and a URL
    recorded in an artifact that no longer matches the URL fetched breaks the
    content-addressing and provenance comparison the artifact exists for.

    Userinfo is out of scope — `https://user:pw@host/` is returned with its
    credential intact — because `validate_url` refuses such a URL outright, so
    nothing this pipeline fetches can carry one. A caller that redacts a URL
    which has not been through that gate does not get that guarantee.
    """
    # Cut at whichever of `?` or `#` comes first: a `?` inside a fragment
    # belongs to the fragment, and treating it as the query separator both
    # mangles the path and drops the `#`.
    cut = next(
        (index for index in sorted(url.find(ch) for ch in "?#") if index >= 0),
        len(url),
    )
    origin, path = _split_origin(url[:cut])
    query, hash_, fragment = url[cut:].partition("#")
    if query.startswith("?"):
        query = "?" + _redact_query(query[1:])
    return (
        f"{_redact_userinfo(origin)}{_redact_path(path)}"
        f"{query}{hash_}{_redact_fragment(fragment)}"
    )


def safe_client(
    *,
    policy: UrlFetchPolicy | None = None,
    resolver: Resolver = _resolve,
    timeout: float | None = None,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    """An `httpx.Client` that validates every request it is about to issue.

    The hook is on `request`, not `response`, and that is the whole point: a
    response hook only ever sees a reply, which means the request already went
    out. httpx fires the request hook for the caller's own URL *and* for each
    redirect hop before issuing it, so one hook covers both — and a caller
    cannot forget to validate, because the client will not send an unvalidated
    request at all.

    Checking only the URL a caller passes would be close to cosmetic anyway: a
    public documentation host answering 302 to `http://127.0.0.1:6379/` bypasses
    that entirely, and `follow_redirects=True` is what every fetcher here uses.
    A relative `Location` needs no special handling, because httpx has already
    resolved it against the previous request by the time the hook runs.

    `trust_env=False` is not optional: with it unset, a proxy environment
    variable routes every fetch through a host the criterion never saw.
    """
    policy = policy or UrlFetchPolicy()

    def _validate_request(request: httpx.Request) -> None:
        validate_url(str(request.url), resolver=resolver)

    return httpx.Client(
        timeout=policy.timeout_seconds if timeout is None else timeout,
        follow_redirects=True,
        max_redirects=policy.max_redirects,
        trust_env=False,
        event_hooks={"request": [_validate_request]},
        transport=transport,
    )


# A URL inside prose. Two things end it, and neither is whitespace: a character
# that cannot appear in a URI at all — Traditional Chinese prose puts the next
# sentence hard against the link, with no space to stop at — and the start of a
# second URL, because `,` is a legal URI character and `a?token=X,https://b`
# would otherwise read as one.
_URI_CHARACTERS = r"[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]"
_URL_IN_TEXT = re.compile(
    rf"(?:https?://|www\.|//)(?:(?!https?://){_URI_CHARACTERS})+",
    re.IGNORECASE,
)
# Punctuation a writer puts *after* a URL rather than in it — a locator reads
# `見 (https://…)。` — trimmed from the end so the redacted form is still the URL
# that was quoted.
_TRAILING_PUNCTUATION = ")]}>,;:.!?'\""


def redact_text(text: str) -> str:
    """Redact every URL that appears inside a larger piece of text.

    Not the same job as `redact_url`, and the difference matters: given
    `見 https://a/?token=X 第 3 節`, `redact_url` reads the words after the URL
    as part of the query value and replaces them along with the credential.
    Prose written by a person or an agent — a citation locator — goes through
    here so only the URL changes.
    """

    def replace(match: re.Match[str]) -> str:
        candidate = match.group(0)
        tail = ""
        while candidate and candidate[-1] in _TRAILING_PUNCTUATION:
            tail = candidate[-1] + tail
            candidate = candidate[:-1]
        return redact_url(candidate) + tail

    return _URL_IN_TEXT.sub(replace, text)


# The seam. A URL is redacted on its way to disk and never in memory: a fetcher
# holds the model before it fetches (`gitbook_llms` reads `page.url` to issue
# the request), so redacting at construction would break acquisition itself.
# Annotating the field rather than calling `redact_url` at each write site moves
# the leak from a forgotten call inside a writer to a wrong type on a model, and
# `tests/test_url_redaction_contract.py` fails on that type.
RedactedUrl = Annotated[str, PlainSerializer(redact_url, return_type=str)]
