from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.rendered_url import import_rendered_url
from loop_apidoc.url_coverage import load_coverage


@pytest.mark.parametrize(
    "url",
    [
        "https://docs.example.com/guide?access_token=s3cret&page=2",
        # `code` is a credential key (an OAuth authorization code), so a language
        # parameter is redacted too. Over-redaction must cost provenance detail
        # and nothing else — it must never break the pipeline.
        "https://docs.example.com/guide?code=en",
    ],
)
def test_a_redacted_coverage_url_still_matches_the_url_the_operator_asked_for(
    tmp_path: Path, url: str
):
    """Issue #156. `import-rendered-url` writes coverage, `scan-sources` reads it
    back and matches it against the same `--url`. Redaction happens on the way
    out, so the two sides only agree if URL identity is redaction-invariant."""
    captured = tmp_path / "page.html"
    captured.write_text("<html></html>", encoding="utf-8")
    sources = tmp_path / "sources"
    coverage_path = tmp_path / "coverage.json"

    import_rendered_url(
        captured,
        original_url=url,
        captured_at="2026-08-30T00:00:00Z",
        capture_method="playwright",
        sources=sources,
        coverage_output=coverage_path,
    )

    manifest = build_manifest(
        sources,
        [url],
        datetime(2026, 8, 30, tzinfo=timezone.utc),
        url_coverage=load_coverage(coverage_path),
    )

    assert len(manifest.url_sources) == 1
    assert "s3cret" not in manifest.model_dump_json()
