from __future__ import annotations

from pathlib import Path

from loop_apidoc.evaluation.models import (
    EvaluationCaseReference,
    EvaluationComparisonReport,
    EvaluationInputError,
    ReplayReport,
    RuntimeReference,
)


def build_comparison_report(
    baseline: ReplayReport,
    candidate: ReplayReport,
) -> EvaluationComparisonReport:
    if (baseline.case_id, baseline.case_version) != (
        candidate.case_id,
        candidate.case_version,
    ):
        raise EvaluationInputError(
            "replay reports must describe the same case id and version"
        )
    return EvaluationComparisonReport(
        case=EvaluationCaseReference(id=baseline.case_id, version=baseline.case_version),
        baseline=_runtime_reference(baseline),
        candidate=_runtime_reference(candidate),
        metrics={
            f"{name}_delta": _delta(
                getattr(candidate.metrics, name), getattr(baseline.metrics, name)
            )
            for name in type(baseline.metrics).model_fields
        },
        cost_delta=_nullable_delta(candidate.cost, baseline.cost),
        latency_ms_delta=_nullable_delta(candidate.latency_ms, baseline.latency_ms),
    )


def render_markdown(report: EvaluationComparisonReport) -> str:
    lines = [
        "# Runtime Evaluation Comparison",
        "",
        f"Case: `{report.case.id}` (version `{report.case.version}`)",
        "",
        "| Metric | Delta (candidate − baseline) |",
        "| --- | ---: |",
    ]
    for name, value in report.metrics.items():
        lines.append(f"| {name} | {value} |")
    lines.extend(
        [
            f"| cost_delta | {_display_optional(report.cost_delta)} |",
            f"| latency_ms_delta | {_display_optional(report.latency_ms_delta)} |",
            "",
            "## Runtimes",
            "",
            f"- Baseline: `{report.baseline.identity}` `{report.baseline.version}` (domain `{report.baseline.domain_version}`)",
            f"- Candidate: `{report.candidate.identity}` `{report.candidate.version}` (domain `{report.candidate.domain_version}`)",
            "",
            "This report is an evaluation artifact only; it does not assemble, import, or approve a contract.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_reports(report: EvaluationComparisonReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation-report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    (output_dir / "evaluation-report.md").write_text(
        render_markdown(report), encoding="utf-8"
    )


def _runtime_reference(report: ReplayReport) -> RuntimeReference:
    return RuntimeReference(
        identity=report.runtime_identity,
        version=report.runtime_version,
        domain_version=report.domain_version,
    )


def _delta(candidate: float, baseline: float) -> float:
    return round(candidate - baseline, 12)


def _nullable_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return _delta(candidate, baseline)


def _display_optional(value: float | None) -> str:
    return "null" if value is None else str(value)
