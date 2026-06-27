from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loop_apidoc.agentcli.adapter import ClaudeCodeAdapter
from loop_apidoc.agentcli.config import AgentConfig
from loop_apidoc.agentcli.extraction import run_agent_extraction
from loop_apidoc.agentcli.preprocess import prepare_markdown
from loop_apidoc.agentcli.runner import subprocess_runner
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.generate.writer import generate_outputs
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.run.models import RunResult, RunStatus
from loop_apidoc.run.persist import persist_plan
from loop_apidoc.validate.report import write_reports
from loop_apidoc.validate.validator import validate_outputs


def run_agent_pipeline(
    *,
    sources_root: Path,
    output_root: Path,
    run_id: str,
    generated_at: datetime,
    executable: str = "claude",
    model: str | None = None,
    urls: list[str] | None = None,
) -> RunResult:
    """Collapsed pipeline using a coding-agent CLI extraction backend.

    manifest (from the original sources) -> PDF->markdown preprocess ->
    collapsed extraction (1 inventory + per-endpoint) -> plan -> generate ->
    validate. A single pass (no correction loop) — the agent extraction is far
    cheaper to simply re-run if needed.
    """
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Manifest is built from the ORIGINAL sources (the PDF) so provenance and
    # single-source attribution still point at the real document.
    manifest = build_manifest(
        sources_root=sources_root, urls=urls or [], generated_at=generated_at
    )
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    # The agent reads a lightweight markdown copy (derived, outside sources/).
    md_dir = prepare_markdown(sources_root, run_dir / "sources_md")
    config = AgentConfig(executable=executable, sources_dir=md_dir, model=model)
    adapter = ClaudeCodeAdapter(config, subprocess_runner(config))

    store = ExtractionStore(run_dir / "extraction")
    extraction = run_agent_extraction(adapter, store)

    plan = build_normalization_plan(extraction, manifest)
    persist_plan(run_dir, plan)
    result = generate_outputs(plan, manifest, run_dir)
    report = validate_outputs(plan, result, manifest)
    write_reports(report, run_dir / "validation")

    return RunResult(
        run_id=run_id,
        run_dir=str(run_dir),
        report=report,
        rounds=0,
        status=RunStatus.PASSED if report.ok else RunStatus.FAILED,
    )
