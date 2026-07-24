from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from loop_apidoc.evaluation.models import EvaluationInputError, ReplayReport


def load_replay_report(path: Path, *, label: str) -> ReplayReport:
    if not path.is_file():
        raise EvaluationInputError(f"{label} replay report does not exist: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvaluationInputError(f"cannot read {label} replay report: {path}") from exc
    try:
        return ReplayReport.model_validate_json(raw)
    except ValidationError as exc:
        raise EvaluationInputError(
            f"{label} replay report schema mismatch: {str(exc)[:200]}"
        ) from exc
