from __future__ import annotations

import pytest

from loop_apidoc.url_safety import (
    UrlFetchPolicy,
    UrlSafetyError,
    validate_url,
)


def _resolver(mapping: dict[str, list[str]]):
    """A stand-in for DNS. Every test injects one, so no test resolves a real
    name — the guard is about what an address turns out to be, and a suite that
    depended on the network could not assert that deterministically."""

    def resolve(host: str, port: int) -> list[str]:
        try:
            return mapping[host]
        except KeyError as exc:  # pragma: no cover - a test naming an unmapped host
            raise AssertionError(f"test resolver has no entry for {host!r}") from exc

    return resolve


PUBLIC = _resolver({"docs.example.com": ["93.184.216.34"]})


def test_a_public_https_url_validates_and_reports_what_it_resolved_to():
    target = validate_url("https://docs.example.com/api", resolver=PUBLIC)

    assert target.host == "docs.example.com"
    assert target.port == 443
    assert target.addresses == ("93.184.216.34",)


def test_the_default_port_follows_the_scheme():
    assert validate_url("http://docs.example.com/x", resolver=PUBLIC).port == 80
    assert (
        validate_url("https://docs.example.com:8443/x", resolver=PUBLIC).port == 8443
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://docs.example.com/x",
        "gopher://docs.example.com/x",
        "data:text/html,hello",
    ],
)
def test_only_http_and_https_are_allowed(url):
    with pytest.raises(UrlSafetyError, match="HTTP"):
        validate_url(url, resolver=PUBLIC)


def test_userinfo_is_refused_rather_than_stripped():
    """Credentials in a URL would otherwise be written verbatim into corpus and
    provenance artifacts. Refusing is the only outcome that cannot leak them."""
    with pytest.raises(UrlSafetyError, match="userinfo"):
        validate_url("https://user:secret@docs.example.com/api", resolver=PUBLIC)


def test_a_url_without_a_host_is_refused():
    with pytest.raises(UrlSafetyError, match="host"):
        validate_url("https:///api", resolver=PUBLIC)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",       # loopback
        "10.0.0.5",        # RFC 1918
        "172.16.0.5",      # RFC 1918
        "192.168.1.5",     # RFC 1918
        "169.254.1.1",     # link-local
        "0.0.0.0",         # unspecified
        "::1",             # IPv6 loopback
        "fc00::1",         # IPv6 unique-local
        "fe80::1",         # IPv6 link-local
    ],
)
def test_a_name_resolving_to_a_non_public_address_is_refused(address):
    resolver = _resolver({"internal.example.com": [address]})

    with pytest.raises(UrlSafetyError, match="non-public"):
        validate_url("https://internal.example.com/x", resolver=resolver)


@pytest.mark.parametrize(
    "address", ["169.254.169.254", "fd00:ec2::254"]
)
def test_the_cloud_metadata_endpoints_are_refused_by_name(address):
    """`fd00:ec2::254` is inside a unique-local range and would be caught anyway,
    but naming both endpoints keeps the intent legible: this is the address an
    SSRF is usually aimed at."""
    resolver = _resolver({"metadata.example.com": [address]})

    with pytest.raises(UrlSafetyError, match="non-public"):
        validate_url("https://metadata.example.com/latest/meta-data/", resolver=resolver)


def test_one_non_public_address_among_several_refuses_the_whole_name():
    """A name that resolves to both a public and a private address is the
    classic bypass: validate the public one, connect to the private one. Every
    address must pass, not any."""
    resolver = _resolver({"split.example.com": ["93.184.216.34", "127.0.0.1"]})

    with pytest.raises(UrlSafetyError, match="non-public"):
        validate_url("https://split.example.com/x", resolver=resolver)


def test_a_literal_ip_is_checked_without_consulting_dns():
    def explode(host: str, port: int) -> list[str]:  # pragma: no cover
        raise AssertionError("a literal address must not be resolved")

    assert validate_url("https://93.184.216.34/x", resolver=explode).addresses == (
        "93.184.216.34",
    )
    with pytest.raises(UrlSafetyError, match="non-public"):
        validate_url("https://127.0.0.1/x", resolver=explode)


def test_a_name_that_resolves_to_nothing_is_refused():
    with pytest.raises(UrlSafetyError, match="non-public"):
        validate_url("https://empty.example.com/x", resolver=_resolver({"empty.example.com": []}))


def test_a_dns_failure_is_reported_without_leaking_the_resolver_message():
    """The exception text reaches logs and reports. Naming the error class is
    enough to diagnose; the resolver's message can carry the queried name and
    search domains."""

    def failing(host: str, port: int) -> list[str]:
        raise OSError("gaierror: internal.corp.example nameserver 10.0.0.1 timed out")

    with pytest.raises(UrlSafetyError) as exc:
        validate_url("https://docs.example.com/x", resolver=failing)

    assert "OSError" in str(exc.value)
    assert "10.0.0.1" not in str(exc.value)


# --- redirect re-validation -------------------------------------------------


import httpx  # noqa: E402

from loop_apidoc.url_safety import safe_client  # noqa: E402


def _transport(handler):
    return httpx.MockTransport(handler)


def _redirecting_to(location: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": location})
        return httpx.Response(200, text="reached")

    return handler


def test_a_redirect_into_a_private_address_is_refused_before_it_is_followed():
    """Validating only the first hop would be nearly cosmetic: a public URL that
    redirects to loopback bypasses it entirely. The hook runs on the 302, before
    httpx issues the next request."""
    client = safe_client(
        resolver=PUBLIC, transport=_transport(_redirecting_to("http://127.0.0.1:6379/x"))
    )

    with pytest.raises(UrlSafetyError, match="non-public"):
        client.get("https://docs.example.com/start")


def test_a_redirect_to_the_metadata_endpoint_is_refused():
    client = safe_client(
        resolver=PUBLIC,
        transport=_transport(
            _redirecting_to("http://169.254.169.254/latest/meta-data/")
        ),
    )

    with pytest.raises(UrlSafetyError, match="non-public"):
        client.get("https://docs.example.com/start")


def test_a_redirect_to_a_non_http_scheme_is_refused():
    client = safe_client(
        resolver=PUBLIC, transport=_transport(_redirecting_to("file:///etc/passwd"))
    )

    with pytest.raises(UrlSafetyError, match="HTTP"):
        client.get("https://docs.example.com/start")


def test_a_redirect_to_another_public_host_is_allowed():
    resolver = _resolver(
        {"docs.example.com": ["93.184.216.34"], "cdn.example.com": ["93.184.216.35"]}
    )
    client = safe_client(
        resolver=resolver,
        transport=_transport(_redirecting_to("https://cdn.example.com/x")),
    )

    assert client.get("https://docs.example.com/start").text == "reached"


def test_a_relative_redirect_is_resolved_against_the_request_before_checking():
    """A bare `/next` has no host of its own; checking it as written would either
    crash or wave it through."""
    client = safe_client(
        resolver=PUBLIC, transport=_transport(_redirecting_to("/next"))
    )

    assert client.get("https://docs.example.com/start").text == "reached"


def test_the_client_caps_the_redirect_chain_at_the_policy_limit():
    def looping(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://docs.example.com/loop"})

    client = safe_client(resolver=PUBLIC, transport=_transport(looping))

    with pytest.raises(httpx.TooManyRedirects):
        client.get("https://docs.example.com/start")
    assert client.max_redirects == UrlFetchPolicy().max_redirects


def test_the_client_ignores_proxy_environment_variables():
    """`manifest/builder.py` built its client without `trust_env=False`, so it
    honoured proxy settings the other seven deliberately ignored."""
    assert safe_client(resolver=PUBLIC, transport=_transport(_redirecting_to("/next"))).trust_env is False


def test_the_client_timeout_comes_from_the_policy_and_can_be_overridden():
    default = safe_client(resolver=PUBLIC)
    assert default.timeout.read == UrlFetchPolicy().timeout_seconds

    assert safe_client(resolver=PUBLIC, timeout=10.0).timeout.read == 10.0


def test_the_initial_request_is_validated_not_only_the_redirects():
    """The response hook only ever sees a reply, which means the request was
    already sent. A client pointed straight at loopback must never issue it."""
    resolver = _resolver({"internal.example.com": ["10.0.0.5"]})
    client = safe_client(
        resolver=resolver, transport=_transport(lambda r: httpx.Response(200, text="x"))
    )

    with pytest.raises(UrlSafetyError, match="non-public"):
        client.get("https://internal.example.com/x")
    with pytest.raises(UrlSafetyError, match="non-public"):
        client.get("http://127.0.0.1:6379/direct")


def test_a_non_http_scheme_is_refused_on_the_initial_request_too():
    client = safe_client(
        resolver=PUBLIC, transport=_transport(lambda r: httpx.Response(200))
    )

    with pytest.raises(UrlSafetyError, match="HTTP"):
        client.get("ftp://docs.example.com/x")


# --- integration: the manifest probe records a refusal rather than crashing --


def test_the_manifest_probe_records_a_refusal_instead_of_raising():
    """`manifest --url` is best-effort metadata gathering and already degrades to
    a note on a network error. A URL the egress policy refuses must degrade the
    same way — visibly, with no digest, so nothing downstream mistakes it for a
    fetched source — rather than aborting the whole manifest build."""
    from loop_apidoc.manifest.urls import probe_url

    client = safe_client(
        resolver=_resolver({"internal.example.com": ["10.0.0.5"]}),
        transport=_transport(lambda r: httpx.Response(200, text="never reached")),
    )

    source = probe_url(
        "https://internal.example.com/api", fetched_at="2026-08-30T00:00:00Z", client=client
    )

    assert source.http_status is None
    assert source.content_sha256 is None
    assert "refused" in (source.note or "")
    assert "10.0.0.5" not in (source.note or "")


# --- refusals must not change a command's error contract --------------------


def test_a_refusal_becomes_a_failed_signal_not_an_escaping_exception():
    """`check-freshness` exits 1 for CHANGED and 2 for INCONCLUSIVE, and CI
    branches on that. An escaping exception exits 1, so a refused fetch would
    read as "sources changed, re-parse" — the opposite of the truth. The honest
    answer is INCONCLUSIVE: we could not determine whether it changed."""
    from loop_apidoc.freshness.signals import fetch_url_signal

    client = safe_client(
        resolver=_resolver({"internal.example.com": ["10.0.0.5"]}),
        transport=_transport(lambda r: httpx.Response(200, text="never reached")),
    )

    observed = fetch_url_signal("https://internal.example.com/x", client=client)

    assert observed.failed is True
    assert observed.signal is None
    assert "refused" in (observed.error or "")


def test_the_openapi_snapshot_reports_a_refusal_as_its_own_error_type(tmp_path):
    """The CLI handler catches `OpenApiSnapshotError` and exits 2 with a clean
    message. An escaping `UrlSafetyError` would print a traceback instead."""
    from loop_apidoc.openapi_snapshot import OpenApiSnapshotError, snapshot_openapi_url

    client = safe_client(
        resolver=PUBLIC, transport=_transport(lambda r: httpx.Response(200, text="{}"))
    )

    with pytest.raises(OpenApiSnapshotError, match="refused"):
        snapshot_openapi_url(
            "http://127.0.0.1:6379/openapi.json",
            sources=tmp_path / "s",
            coverage_output=tmp_path / "c.json",
            client=client,
        )


def test_the_gitbook_cache_reports_a_refusal_as_its_own_error_type(tmp_path):
    from loop_apidoc.gitbook_llms import GitBookLlmsError, cache_gitbook_llms

    client = safe_client(
        resolver=PUBLIC, transport=_transport(lambda r: httpx.Response(200, text="x"))
    )

    with pytest.raises(GitBookLlmsError, match="refused"):
        cache_gitbook_llms(
            "http://127.0.0.1:6379/docs",
            sources=tmp_path / "s",
            coverage_output=tmp_path / "c.json",
            client=client,
        )


@pytest.mark.parametrize(
    ("address", "why"),
    [
        ("64:ff9b::a9fe:a9fe", "NAT64 well-known prefix embedding 169.254.169.254"),
        ("64:ff9b::7f00:1", "NAT64 embedding 127.0.0.1"),
        ("192.88.99.1", "6to4 relay anycast"),
        ("224.0.0.1", "IPv4 multicast"),
        ("ff02::1", "IPv6 link-local multicast"),
    ],
)
def test_addresses_python_calls_global_but_are_not_safe_targets(address, why):
    """`ipaddress.is_global` means "not flagged non-global in a special-purpose
    registry", which is close to but not the same as "safe to connect to".
    RFC 6052's NAT64 prefix is the sharp one: its low 32 bits are an arbitrary
    IPv4, so on a network with a NAT64 gateway an AAAA of `64:ff9b::a9fe:a9fe`
    reaches the metadata endpoint while every layer reports "globally routable"."""
    resolver = _resolver({"host.example.com": [address]})

    with pytest.raises(UrlSafetyError, match="non-public"):
        validate_url("https://host.example.com/x", resolver=resolver)


def test_the_policy_is_frozen_and_carries_the_documented_bounds():
    policy = UrlFetchPolicy()

    assert policy.max_redirects == 5
    assert policy.timeout_seconds == 20.0
    with pytest.raises(Exception):
        policy.max_redirects = 1  # type: ignore[misc]
