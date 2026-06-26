from __future__ import annotations

from pathlib import Path

import loop_apidoc.run.pipeline as pipeline
from loop_apidoc.extraction.models import ExtractionResult
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport


def _endpoint_report() -> ValidationReport:
    return ValidationReport(issues=[Issue(
        code=IssueCode.REQUIRED_INFO_MISSING, severity=Severity.ERROR,
        location="paths./u.get", evidence="no responses", suggested_fix="add")])


def _unmappable_report() -> ValidationReport:
    # An actionable RE_QUERY issue whose location matches no stage prefix.
    return ValidationReport(issues=[Issue(
        code=IssueCode.REQUIRED_INFO_MISSING, severity=Severity.ERROR,
        location="mystery.location", evidence="x", suggested_fix="y")])


def _patch_common(monkeypatch):
    sentinel = ExtractionResult(notebook_url="nb")
    monkeypatch.setattr(pipeline, "build_normalization_plan",
                        lambda extraction, manifest: "PLAN")
    monkeypatch.setattr(pipeline, "_persist_plan", lambda run_dir, plan: None)
    return sentinel


def test_requery_targets_mapped_stages(monkeypatch, tmp_path: Path) -> None:
    sentinel = _patch_common(monkeypatch)
    calls = {}
    monkeypatch.setattr(pipeline, "rerun_stages",
                        lambda *a, **k: calls.__setitem__("rerun", a) or sentinel)
    monkeypatch.setattr(pipeline, "run_extraction",
                        lambda *a, **k: calls.__setitem__("full", True) or sentinel)

    state = {"extraction": ExtractionResult(notebook_url="nb")}
    requery = pipeline._make_requery(
        adapter=object(), notebook_url="nb", store=object(),
        manifest=object(), run_dir=tmp_path, state=state)

    new_plan = requery("oldplan", _endpoint_report())

    assert new_plan == "PLAN"
    assert "rerun" in calls and "full" not in calls
    # positional args: (adapter, notebook_url, store, prior, stage_ids)
    assert calls["rerun"][4] == {"05", "06"}
    assert state["extraction"] is sentinel  # holder updated for next round


def test_requery_falls_back_to_full_when_unmappable(monkeypatch, tmp_path: Path) -> None:
    sentinel = _patch_common(monkeypatch)
    calls = {}
    monkeypatch.setattr(pipeline, "rerun_stages",
                        lambda *a, **k: calls.__setitem__("rerun", True) or sentinel)
    monkeypatch.setattr(pipeline, "run_extraction",
                        lambda *a, **k: calls.__setitem__("full", a) or sentinel)

    state = {"extraction": ExtractionResult(notebook_url="nb")}
    requery = pipeline._make_requery(
        adapter=object(), notebook_url="nb", store=object(),
        manifest=object(), run_dir=tmp_path, state=state)

    requery("oldplan", _unmappable_report())

    assert "full" in calls and "rerun" not in calls
    assert state["extraction"] is sentinel
