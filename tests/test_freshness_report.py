from pathlib import Path

from loop_apidoc.freshness.models import (
    FreshnessReport,
    FreshnessVerdict,
    SourceKind,
    SourceResult,
    SourceStatus,
)
from loop_apidoc.freshness.report import render_markdown, write_reports


def _report():
    return FreshnessReport(
        verdict=FreshnessVerdict.CHANGED,
        openapi_version="2.3.0",
        sources_total=2,
        unchanged_count=1,
        changed=[SourceResult(id="https://api/x", kind=SourceKind.OPENAPI_URL,
                              status=SourceStatus.CHANGED, reason="version 2.3.0 -> 2.4.0")],
        inconclusive=[],
    )


def test_render_markdown_mentions_verdict_and_reason():
    md = render_markdown(_report())
    assert "changed" in md
    assert "version 2.3.0 -> 2.4.0" in md


def test_write_reports(tmp_path: Path):
    json_path, md_path = write_reports(_report(), tmp_path)
    assert json_path.exists() and md_path.exists()
    assert '"verdict": "changed"' in json_path.read_text(encoding="utf-8")
    assert md_path.read_text(encoding="utf-8").startswith("#")
