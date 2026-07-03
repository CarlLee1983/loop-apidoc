from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import Manifest, UrlSource
from loop_apidoc.plan.models import IntegrationContract, NormalizationPlan
from loop_apidoc.preparation import assess_preparation
from loop_apidoc.preparation.coverage import UrlCoverage

_NOW = datetime(2026, 7, 3, 8, 0, tzinfo=timezone.utc)


def _manifest_with_urls() -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        url_sources=[
            UrlSource(url="https://docs.example.com/api/", fetched_at=_NOW, http_status=200)
        ],
    )


def _manifest_local_only() -> Manifest:
    return Manifest(sources_root="./sources", generated_at=_NOW)


def _inventory() -> dict:
    return {"title": "Demo", "endpoints": [{"method": "GET", "path": "/ping"}], "missing": []}


def _endpoint() -> str:
    import json
    return json.dumps({"method": "GET", "path": "/ping", "responses": [], "missing": []})


def _plan() -> NormalizationPlan:
    return NormalizationPlan(notebook_url="", integration=IntegrationContract())


def _assess(manifest, coverage):
    return assess_preparation(
        manifest=manifest,
        inventory=_inventory(),
        endpoint_texts=[_endpoint()],
        plan=_plan(),
        url_coverage=coverage,
    )


def _url_phase(report):
    return next((p for p in report.phases if p.id == "url_coverage"), None)


def test_phase_absent_when_no_url_sources():
    report = _assess(_manifest_local_only(), None)
    assert _url_phase(report) is None
    assert [p.id for p in report.phases] == [
        "sources", "extraction", "normalization_plan", "integration_contract",
    ]


def test_full_coverage_has_phase_but_no_findings():
    coverage = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[{"url": "https://docs.example.com/api/auth", "source": "nav"}],
        results=[{"url": "https://docs.example.com/api/auth", "status": "fetched",
                  "file": "url_sources/auth.md", "method": "defuddle"}],
    )
    phase = _url_phase(_assess(_manifest_with_urls(), coverage))
    assert phase is not None
    assert phase.findings == []


def test_missing_coverage_file_warns():
    phase = _url_phase(_assess(_manifest_with_urls(), None))
    assert phase is not None
    assert len(phase.findings) == 1
    assert phase.findings[0].severity.value == "warning"
    assert "coverage.json" in phase.findings[0].summary


def test_fetch_failed_and_empty_suspect_warn():
    coverage = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[
            {"url": "https://docs.example.com/api/a", "source": "nav"},
            {"url": "https://docs.example.com/api/b", "source": "nav"},
        ],
        results=[
            {"url": "https://docs.example.com/api/a", "status": "fetch_failed"},
            {"url": "https://docs.example.com/api/b", "status": "empty_suspect",
             "file": "url_sources/b.md", "method": "playwright"},
        ],
    )
    phase = _url_phase(_assess(_manifest_with_urls(), coverage))
    summaries = " || ".join(f.summary for f in phase.findings)
    assert "https://docs.example.com/api/a" in summaries
    assert "https://docs.example.com/api/b" in summaries
    assert all(f.severity.value == "warning" for f in phase.findings)


def test_auth_required_without_file_warns_but_with_file_is_clean():
    with_file = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[{"url": "https://docs.example.com/api/secure", "source": "nav"}],
        results=[{"url": "https://docs.example.com/api/secure", "status": "auth_required",
                  "file": "secure.pdf"}],
    )
    assert _url_phase(_assess(_manifest_with_urls(), with_file)).findings == []

    without_file = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[{"url": "https://docs.example.com/api/secure", "source": "nav"}],
        results=[{"url": "https://docs.example.com/api/secure", "status": "auth_required"}],
    )
    findings = _url_phase(_assess(_manifest_with_urls(), without_file)).findings
    assert len(findings) == 1
    assert "secure" in findings[0].summary


def test_expected_page_never_fetched_warns():
    coverage = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[
            {"url": "https://docs.example.com/api/seen", "source": "nav"},
            {"url": "https://docs.example.com/api/ghost", "source": "nav"},
        ],
        results=[{"url": "https://docs.example.com/api/seen", "status": "fetched",
                  "file": "url_sources/seen.md", "method": "defuddle"}],
    )
    phase = _url_phase(_assess(_manifest_with_urls(), coverage))
    assert any("ghost" in f.summary for f in phase.findings)
    assert phase.metrics["not_fetched"] == 1


def test_unconfirmed_list_warns():
    coverage = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=False,
        expected=[{"url": "https://docs.example.com/api/auth", "source": "nav"}],
        results=[{"url": "https://docs.example.com/api/auth", "status": "fetched",
                  "file": "url_sources/auth.md", "method": "defuddle"}],
    )
    phase = _url_phase(_assess(_manifest_with_urls(), coverage))
    assert any("confirm" in f.summary.lower() for f in phase.findings)


def test_duplicate_expected_urls_warn_once():
    coverage = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[
            {"url": "https://docs.example.com/api/ghost", "source": "nav"},
            {"url": "https://docs.example.com/api/ghost", "source": "sitemap"},
        ],
        results=[],
    )
    phase = _url_phase(_assess(_manifest_with_urls(), coverage))
    ghost_findings = [f for f in phase.findings if "ghost" in f.summary]
    assert len(ghost_findings) == 1
    assert phase.metrics["not_fetched"] == 1


def test_url_matching_ignores_trailing_slash_and_fragment():
    coverage = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[
            {"url": "https://docs.example.com/api/auth/", "source": "nav"},
            {"url": "https://docs.example.com/api/pay#request", "source": "nav"},
        ],
        results=[
            {"url": "https://docs.example.com/api/auth", "status": "fetched",
             "file": "url_sources/auth.md", "method": "defuddle"},
            {"url": "https://docs.example.com/api/pay", "status": "fetched",
             "file": "url_sources/pay.md", "method": "defuddle"},
        ],
    )
    phase = _url_phase(_assess(_manifest_with_urls(), coverage))
    assert phase.findings == []
    assert phase.metrics["not_fetched"] == 0


def test_skipped_by_user_is_not_a_finding():
    coverage = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[{"url": "https://docs.example.com/api/legacy", "source": "nav"}],
        results=[{"url": "https://docs.example.com/api/legacy", "status": "skipped_by_user"}],
    )
    phase = _url_phase(_assess(_manifest_with_urls(), coverage))
    assert phase.findings == []
