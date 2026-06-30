from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.generate.writer import generate_outputs
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import EndpointEntry, NormalizationPlan


def _manifest() -> Manifest:
    return Manifest(
        sources_root=".",
        generated_at=datetime(2026, 6, 28, tzinfo=timezone.utc),
    )


def _plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="x",
        endpoints=[
            EndpointEntry(
                status="supported",
                method="POST",
                path="/pay",
                summary="付款",
                request={"content_type": "application/json"},
            )
        ],
    )


def test_generate_outputs_writes_example_files(tmp_path: Path):
    result = generate_outputs(_plan(), _manifest(), tmp_path)
    assert result.examples, "result.examples should be non-empty dict"
    sh = list(tmp_path.glob("examples/*/request.sh"))
    assert sh, "expected at least one request.sh under examples/"
    assert (tmp_path / "examples" / "README.md").exists()
    assert "NOT a source document" in sh[0].read_text(encoding="utf-8")


def test_generate_outputs_writes_review_html(tmp_path: Path):
    generate_outputs(_plan(), _manifest(), tmp_path)

    review = tmp_path / "review.html"

    assert review.exists()
    html = review.read_text(encoding="utf-8")
    assert 'class="review-dashboard"' in html
    assert 'href="openapi.yaml"' in html
    assert 'href="api-guide.zh-TW.md"' in html
    assert 'href="provenance.json"' in html
    assert "POST" in html
    assert "/pay" in html
