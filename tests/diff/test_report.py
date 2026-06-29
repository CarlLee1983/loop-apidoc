from __future__ import annotations

from loop_apidoc.diff.models import DiffFinding, DiffImpact, DiffReport
from loop_apidoc.diff.report import render_markdown, write_reports


def _report() -> DiffReport:
    return DiffReport(
        base_run="output/base",
        head_run="output/head",
        summary={"breaking": 1, "additive": 1, "changed": 0, "source_only": 1},
        findings=[
            DiffFinding(
                impact=DiffImpact.BREAKING,
                area="openapi.responses",
                location="POST /payments responses.400",
                summary="response removed",
                before={"description": "bad"},
            ),
            DiffFinding(
                impact=DiffImpact.ADDITIVE,
                area="openapi.paths",
                location="POST /refunds",
                summary="operation added",
                after={"responses": {"200": {"description": "ok"}}},
            ),
            DiffFinding(
                impact=DiffImpact.SOURCE_ONLY,
                area="provenance",
                location="paths./payments.post",
                summary="provenance changed",
            ),
        ],
    )


def test_render_markdown_groups_by_impact_and_includes_counts():
    md = render_markdown(_report())

    assert "# Version Diff Report" in md
    assert "Base: `output/base`" in md
    assert "| breaking | 1 |" in md
    assert "## Breaking" in md
    assert "`POST /payments responses.400`: response removed" in md
    assert "## Additive" in md
    assert "## Source Only" in md


def test_write_reports_emits_json_and_markdown(tmp_path):
    out = tmp_path / "diff"
    write_reports(_report(), out)

    loaded = DiffReport.model_validate_json((out / "report.json").read_text())
    assert loaded == _report()
    assert "Version Diff Report" in (out / "report.md").read_text(encoding="utf-8")
