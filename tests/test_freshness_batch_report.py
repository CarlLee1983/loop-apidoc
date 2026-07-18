from pathlib import Path

from loop_apidoc.freshness.models import (
    BatchItemResult,
    BatchItemStatus,
    BatchReport,
    FreshnessVerdict,
)
from loop_apidoc.freshness.report import render_batch_markdown, write_batch_reports


def _report():
    return BatchReport(
        verdict=FreshnessVerdict.CHANGED, total=2, changed_count=1, attention_count=1, unchanged_count=0,
        items=[
            BatchItemResult(label="stripe", status=BatchItemStatus.CHANGED, openapi_version="1.0.0",
                            reason="https://api/x: version 1.0.0 -> 2.0.0"),
            BatchItemResult(label="ghost", status=BatchItemStatus.ERROR, reason="fingerprint not found"),
        ],
    )


def test_render_batch_markdown_lists_items_and_reasons():
    md = render_batch_markdown(_report())
    assert "changed" in md
    assert "stripe" in md and "ghost" in md
    assert "version 1.0.0 -> 2.0.0" in md


def test_write_batch_reports(tmp_path: Path):
    j, m = write_batch_reports(_report(), tmp_path)
    assert j.name == "freshness-scan.json" and m.name == "freshness-scan.md"
    assert '"verdict": "changed"' in j.read_text(encoding="utf-8")
    assert m.read_text(encoding="utf-8").startswith("#")
