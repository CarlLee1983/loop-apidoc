from pathlib import Path

import httpx

from loop_apidoc.freshness.models import (
    FingerprintEntry,
    FreshnessVerdict,
    SourceFingerprint,
    SourceKind,
    SourceSignal,
    SourceStatus,
)
from loop_apidoc.freshness.check import check_freshness


def _fp(*entries, openapi_version="2.3.0"):
    return SourceFingerprint(openapi_version=openapi_version, sources=list(entries))


def _openapi_entry(version, sha="old", etag=None):
    return FingerprintEntry(
        id="https://api.example.com/openapi.json",
        kind=SourceKind.OPENAPI_URL,
        signal=SourceSignal(version=version, sha256=sha, etag=etag),
    )


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


def test_unchanged_when_version_matches():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json"},
                              content=b'{"openapi":"3.1.0","info":{"version":"2.3.0"}}')

    report = check_freshness(_fp(_openapi_entry("2.3.0")), client=_client(handler))
    assert report.verdict is FreshnessVerdict.UNCHANGED
    assert report.unchanged_count == 1
    assert report.sources_total == 1


def test_changed_on_version_bump():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json"},
                              content=b'{"openapi":"3.1.0","info":{"version":"2.4.0"}}')

    report = check_freshness(_fp(_openapi_entry("2.3.0")), client=_client(handler))
    assert report.verdict is FreshnessVerdict.CHANGED
    assert report.changed[0].reason == "version 2.3.0 -> 2.4.0"


def test_changed_dominates_inconclusive():
    def handler(request):
        if "openapi" in str(request.url):
            return httpx.Response(200, headers={"content-type": "application/json"},
                                  content=b'{"openapi":"3.1.0","info":{"version":"2.4.0"}}')
        return httpx.Response(500)

    web = FingerprintEntry(id="https://docs.example.com/x", kind=SourceKind.WEB_URL,
                           signal=SourceSignal(sha256="a"))
    report = check_freshness(_fp(_openapi_entry("2.3.0"), web), client=_client(handler))
    assert report.verdict is FreshnessVerdict.CHANGED
    assert len(report.inconclusive) == 1


def test_web_fetch_failure_is_inconclusive():
    def handler(request):
        return httpx.Response(503)

    web = FingerprintEntry(id="https://docs.example.com/x", kind=SourceKind.WEB_URL,
                           signal=SourceSignal(sha256="a"))
    report = check_freshness(_fp(web), client=_client(handler))
    assert report.verdict is FreshnessVerdict.INCONCLUSIVE
    assert report.inconclusive[0].status is SourceStatus.FETCH_FAILED


def test_local_file_unchanged(tmp_path: Path):
    f = tmp_path / "spec.pdf"
    f.write_bytes(b"hello")
    from loop_apidoc.freshness.signals import hash_bytes
    entry = FingerprintEntry(id="spec.pdf", kind=SourceKind.LOCAL_FILE,
                             signal=SourceSignal(sha256=hash_bytes(b"hello")))
    report = check_freshness(_fp(entry), sources_root=tmp_path)
    assert report.verdict is FreshnessVerdict.UNCHANGED


def test_local_file_missing_root_is_inconclusive():
    entry = FingerprintEntry(id="spec.pdf", kind=SourceKind.LOCAL_FILE,
                             signal=SourceSignal(sha256="x"))
    report = check_freshness(_fp(entry), sources_root=None)
    assert report.verdict is FreshnessVerdict.INCONCLUSIVE


def test_observed_source_bytes_are_not_serialized_in_freshness_report(tmp_path: Path):
    source = tmp_path / "spec.md"
    source.write_text("current source", encoding="utf-8")
    from loop_apidoc.freshness.signals import hash_bytes

    entry = FingerprintEntry(
        id="spec.md",
        kind=SourceKind.LOCAL_FILE,
        signal=SourceSignal(sha256=hash_bytes(b"previous source")),
    )

    report = check_freshness(_fp(entry), sources_root=tmp_path)

    assert report.observations[0].raw == b"current source"
    assert "observations" not in report.model_dump()
    assert "current source" not in report.model_dump_json()
