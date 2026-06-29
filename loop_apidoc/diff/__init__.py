"""Run-to-run diff support for generated loop-apidoc artifacts."""

from loop_apidoc.diff.compare import build_diff_report
from loop_apidoc.diff.loader import DiffInputError, RunArtifacts, load_run_artifacts
from loop_apidoc.diff.models import DiffFinding, DiffImpact, DiffReport
from loop_apidoc.diff.report import render_markdown, write_reports

__all__ = [
    "DiffFinding",
    "DiffImpact",
    "DiffInputError",
    "DiffReport",
    "RunArtifacts",
    "build_diff_report",
    "load_run_artifacts",
    "render_markdown",
    "write_reports",
]
