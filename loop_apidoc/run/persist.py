from __future__ import annotations

from pathlib import Path


def persist_plan(run_dir: Path, plan) -> None:
    """Write the normalization plan into the run dir's plan/ subdir."""
    plan_dir = run_dir / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "normalization-plan.json").write_text(
        plan.model_dump_json(indent=2), encoding="utf-8"
    )
