from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from loop_apidoc.freshness.signals import hash_bytes
from loop_apidoc.governance.models import (
    GovernanceReport,
    GovernanceReviewItem,
    GovernanceReviewPlan,
    GovernanceReviewSource,
    GovernanceSnapshot,
    GovernanceTriggerKind,
)


class GovernanceReviewPlanError(ValueError):
    """A governance trigger or snapshot cannot form a bounded review handoff."""


_CHANGED_STEPS = [
    "Review the retained source bytes against the changed-source trigger.",
    "Re-extract into a separate work directory and run verify-extraction.",
    "Assemble, inspect the impact diff, then request explicit human approval.",
]


def load_review_plan_inputs(
    trigger_path: Path, snapshot_dir: Path | None
) -> tuple[GovernanceReport, GovernanceSnapshot | None]:
    report = _load_model(GovernanceReport, trigger_path, "governance trigger")
    if snapshot_dir is None:
        return report, None
    snapshot_path = snapshot_dir / "governance-snapshot.json"
    snapshot = _load_model(GovernanceSnapshot, snapshot_path, "governance snapshot")
    _verify_snapshot_bytes(snapshot, snapshot_dir)
    return report, snapshot


def build_review_plan(
    report: GovernanceReport, snapshot: GovernanceSnapshot | None
) -> GovernanceReviewPlan:
    by_label = {item.label: item.sources for item in snapshot.items} if snapshot else {}
    items = []
    for trigger in report.triggers:
        sources = [
            GovernanceReviewSource(id=source.id, sha256=source.sha256, path=source.path)
            for source in by_label.get(trigger.label, [])
        ]
        if trigger.kind is GovernanceTriggerKind.SOURCE_CHANGED and not sources:
            raise GovernanceReviewPlanError(
                f"changed trigger requires a verified snapshot: {trigger.label}"
            )
        steps = _CHANGED_STEPS if trigger.kind is GovernanceTriggerKind.SOURCE_CHANGED else [
            "Investigate the inconclusive freshness result before re-extraction.",
            "Do not assemble or approve until source availability is resolved.",
        ]
        items.append(GovernanceReviewItem(
            label=trigger.label,
            kind=trigger.kind,
            reason=trigger.reason,
            run_dir=trigger.run_dir,
            sources=sources,
            required_steps=steps,
        ))
    return GovernanceReviewPlan(items=items)


def render_markdown(plan: GovernanceReviewPlan) -> str:
    lines = ["# Governance Review Plan", ""]
    for item in plan.items:
        lines.extend([f"## {item.label}", "", f"- Trigger: `{item.kind.value}`"])
        if item.reason:
            lines.append(f"- Reason: {item.reason}")
        if item.run_dir:
            lines.append(f"- Previous run: `{item.run_dir}`")
        for source in item.sources:
            lines.append(f"- Snapshot: `{source.path}` (`{source.sha256}`)")
        lines.extend(["", "Required manual/agent steps:", ""])
        lines.extend(f"1. {step}" for step in item.required_steps)
        lines.append("")
    return "\n".join(lines)


def write_review_plan(plan: GovernanceReviewPlan, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "governance-review-plan.json").write_text(
        plan.model_dump_json(indent=2), encoding="utf-8"
    )
    (output_dir / "governance-review-plan.md").write_text(
        render_markdown(plan), encoding="utf-8"
    )


def _load_model(model: type[GovernanceReport] | type[GovernanceSnapshot], path: Path, label: str):
    if not path.is_file():
        raise GovernanceReviewPlanError(f"{label} does not exist: {path}")
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise GovernanceReviewPlanError(f"invalid {label}: {path}") from exc


def _verify_snapshot_bytes(snapshot: GovernanceSnapshot, snapshot_dir: Path) -> None:
    for item in snapshot.items:
        for source in item.sources:
            path = snapshot_dir / source.path
            try:
                raw = path.read_bytes()
            except OSError as exc:
                raise GovernanceReviewPlanError(f"snapshot source missing: {source.path}") from exc
            if hash_bytes(raw) != source.sha256:
                raise GovernanceReviewPlanError(f"snapshot source digest mismatch: {source.path}")
