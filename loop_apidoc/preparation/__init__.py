"""Pre-generation readiness checks for source-grounded API documentation runs."""

from loop_apidoc.preparation.assess import assess_preparation
from loop_apidoc.preparation.coverage import (
    CoverageInputError,
    UrlCoverage,
    load_coverage,
)
from loop_apidoc.preparation.models import (
    PreparationFinding,
    PreparationPhase,
    PreparationReport,
    PreparationSeverity,
    PreparationStatus,
)
from loop_apidoc.preparation.report import render_markdown, write_reports

__all__ = [
    "CoverageInputError",
    "PreparationFinding",
    "PreparationPhase",
    "PreparationReport",
    "PreparationSeverity",
    "PreparationStatus",
    "UrlCoverage",
    "assess_preparation",
    "load_coverage",
    "render_markdown",
    "write_reports",
]
