from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from collections.abc import Sequence

from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.source_quality.assess import assess_source_quality
from loop_apidoc.source_quality.models import SourceDiffReport
from loop_apidoc.source_quality.report import write_reports
from loop_apidoc.source_risk import inspect_source_risks


def write_passing_source_quality(
    *,
    sources_root: Path,
    output: Path,
    generated_at: datetime,
    excludes: Sequence[str] = (),
    source_set: str = "test-source-set",
) -> Path:
    """Create the complete, current pass package required by assemble tests."""
    manifest = build_manifest(
        sources_root=sources_root,
        urls=[],
        generated_at=generated_at,
        excludes=excludes,
    )
    manifest_bytes = manifest.model_dump_json().encode("utf-8")
    source_risk = inspect_source_risks(
        sources_root=sources_root,
        manifest=manifest,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        max_bytes=5 * 1024 * 1024,
    )
    assert source_risk.verdict.value == "pass"
    report = assess_source_quality(
        manifest=manifest,
        source_set=source_set,
        observations=[],
        base_report=None,
        source_risk=source_risk,
    )
    assert report.verdict.value == "pass"
    write_reports(report, SourceDiffReport(), output)
    return output
