from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loop_apidoc.extraction.orchestrator import rerun_stages, run_extraction
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.generate.writer import generate_outputs
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.run.correction import annotate_fixability, run_correction_loop
from loop_apidoc.run.models import RunResult, RunStatus
from loop_apidoc.run.requery import stages_for_requery
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport
from loop_apidoc.validate.report import write_reports
from loop_apidoc.validate.validator import validate_outputs


def _make_requery(*, adapter, notebook_url, store, manifest, run_dir, state):
    """Build the correction-loop requery closure.

    Targets only the stages the report's actionable RE_QUERY issues map to;
    falls back to a full re-extraction when none can be pinned. `state` holds
    the current ExtractionResult and is updated in place so each round re-runs
    against the latest extraction.
    """
    def requery(_p, r):
        # The prior plan is intentionally ignored: each requery rebuilds the
        # plan from the freshly merged extraction rather than patching `_p`.
        stages = stages_for_requery(r)
        if stages:
            fresh = rerun_stages(adapter, notebook_url, store, state["extraction"], stages)
        else:
            fresh = run_extraction(adapter, notebook_url, store)
        state["extraction"] = fresh
        new_plan = build_normalization_plan(fresh, manifest)
        _persist_plan(run_dir, new_plan)
        return new_plan

    return requery


def _auth_blocked_report() -> ValidationReport:
    return ValidationReport(
        issues=[
            Issue(
                code=IssueCode.SOURCE_UNVERIFIED,
                severity=Severity.ERROR,
                location="notebooklm.auth",
                evidence="NotebookLM 未驗證；請先登入。",
                suggested_fix="執行 notebooklm-skill 登入流程後重試。",
            )
        ]
    )


def run_pipeline(
    *,
    notebook_url: str,
    sources_root: Path,
    output_root: Path,
    adapter: NotebookLMAdapter,
    run_id: str,
    generated_at: datetime,
    urls: list[str] | None = None,
    max_rounds: int = 3,
) -> RunResult:
    """Run the full source-grounded doc pipeline into output_root/run_id."""
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(
        sources_root=sources_root, urls=urls or [], generated_at=generated_at
    )
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    status = adapter.auth_status()
    if not status.authenticated:
        report = annotate_fixability(_auth_blocked_report())
        write_reports(report, run_dir / "validation")
        return RunResult(
            run_id=run_id,
            run_dir=str(run_dir),
            report=report,
            rounds=0,
            status=RunStatus.BLOCKED,
        )

    store = ExtractionStore(run_dir / "extraction")
    extraction = run_extraction(adapter, notebook_url, store)
    state = {"extraction": extraction}
    plan = build_normalization_plan(extraction, manifest)
    _persist_plan(run_dir, plan)

    result = generate_outputs(plan, manifest, run_dir)

    def regenerate(p):
        return generate_outputs(p, manifest, run_dir)

    def validate(p, r):
        return validate_outputs(p, r, manifest)

    requery = _make_requery(
        adapter=adapter, notebook_url=notebook_url, store=store,
        manifest=manifest, run_dir=run_dir, state=state,
    )

    outcome = run_correction_loop(
        plan,
        result,
        regenerate=regenerate,
        requery=requery,
        validate=validate,
        max_rounds=max_rounds,
    )

    write_reports(outcome.report, run_dir / "validation")
    _persist_plan(run_dir, outcome.plan)
    return RunResult(
        run_id=run_id,
        run_dir=str(run_dir),
        report=outcome.report,
        rounds=outcome.rounds,
        status=outcome.status,
    )


def _persist_plan(run_dir: Path, plan) -> None:
    plan_dir = run_dir / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "normalization-plan.json").write_text(
        plan.model_dump_json(indent=2), encoding="utf-8"
    )
