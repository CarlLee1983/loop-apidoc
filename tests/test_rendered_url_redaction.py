from __future__ import annotations

from pathlib import Path

from loop_apidoc.rendered_url import import_rendered_url


def test_import_rendered_url_writes_no_credential_into_provenance_or_coverage(tmp_path: Path):
    """Issue #156. The provenance sidecar is a hand-built dict rather than a
    model dump, so it needs its own regression: the annotated field on
    `RenderedProvenance` does not cover it."""
    captured = tmp_path / "page.html"
    captured.write_text("<html></html>", encoding="utf-8")

    import_rendered_url(
        captured,
        original_url="https://docs.example.com/guide?access_token=s3cret&page=2",
        captured_at="2026-08-30T00:00:00Z",
        capture_method="playwright",
        sources=tmp_path / "sources",
        coverage_output=tmp_path / "coverage.json",
    )

    written = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(tmp_path.rglob("*"))
        if path.is_file()
    )
    assert "s3cret" not in written
    assert "access_token=[REDACTED]" in written
    assert "page=2" in written
