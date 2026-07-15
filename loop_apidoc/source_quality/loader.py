from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.source_quality.models import (
    QualityObservation,
    SourceDiffReport,
    SourceQualityReport,
)


class SourceQualityInputError(ValueError):
    pass


def load_manifest(path: Path) -> Manifest:
    try:
        return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise SourceQualityInputError(f"invalid manifest: {path}: {exc}") from exc


def load_observations(path: Path) -> list[QualityObservation]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("observations must be a JSON array")
        return [QualityObservation.model_validate(item) for item in payload]
    except (OSError, ValueError, ValidationError) as exc:
        raise SourceQualityInputError(f"invalid observations: {path}: {exc}") from exc


def load_assessment_reports(path: Path) -> tuple[SourceQualityReport, SourceDiffReport]:
    """Load the complete output directory created by ``assess-sources``."""
    report_path = path / "source-quality-report.json"
    diff_path = path / "source-diff.json"
    try:
        report = SourceQualityReport.model_validate_json(
            report_path.read_text(encoding="utf-8")
        )
        diff = SourceDiffReport.model_validate_json(diff_path.read_text(encoding="utf-8"))
        return report, diff
    except (OSError, ValidationError) as exc:
        raise SourceQualityInputError(
            f"invalid source quality reports: {path}: {exc}"
        ) from exc
