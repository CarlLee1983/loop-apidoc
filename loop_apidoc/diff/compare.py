from __future__ import annotations

from loop_apidoc.diff.loader import RunArtifacts
from loop_apidoc.diff.models import DiffReport


def build_diff_report(base: RunArtifacts, head: RunArtifacts) -> DiffReport:
    return DiffReport(
        base_run=str(base.run_dir),
        head_run=str(head.run_dir),
        summary={"breaking": 0, "additive": 0, "changed": 0, "source_only": 0},
        findings=[],
    )
