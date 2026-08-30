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
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

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
