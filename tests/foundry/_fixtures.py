from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.score.models import ScoreProfile, ScoreReport, ScoreStatus
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "paths": {"/ping": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }


def write_run_dir(
    run_dir: Path,
    *,
    validation_ok: bool = True,
    score: int | None = 92,
    with_integration: bool = True,
) -> Path:
    """Materialize a completed run dir accepted by diff.load_run_artifacts."""
    run_dir.mkdir(parents=True)
    (run_dir / "openapi.yaml").write_text(
        yaml.safe_dump(_openapi(), sort_keys=False), encoding="utf-8"
    )
    provenance = ProvenanceDocument(
        notebook_url="",
        entries=[
            ProvenanceEntry(
                target="paths./ping.get",
                status=PlanItemStatus.SUPPORTED,
                manifest_source="manual.md",
                query_id="06",
                answer_path="answers/06.txt",
                locator="p.1",
            )
        ],
    )
    (run_dir / "provenance.json").write_text(
        provenance.model_dump_json(indent=2), encoding="utf-8"
    )
    validation_dir = run_dir / "validation"
    validation_dir.mkdir()
    report = ValidationReport() if validation_ok else _failing_report()
    (validation_dir / "report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    (validation_dir / "report.md").write_text("# Validation\n", encoding="utf-8")
    manifest = Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=10,
                sha256="hash-manual",
                scanned_at=_NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    (run_dir / "review.html").write_text("<html></html>", encoding="utf-8")
    if with_integration:
        (run_dir / "integration-contract.json").write_text(
            '{"payloads": []}', encoding="utf-8"
        )
    if score is not None:
        score_dir = run_dir / "score"
        score_dir.mkdir()
        (score_dir / "score.json").write_text(
            _score_json(score), encoding="utf-8"
        )
        (score_dir / "score.md").write_text("# Score\n", encoding="utf-8")
    handoff_dir = run_dir / "handoff"
    handoff_dir.mkdir()
    (handoff_dir / "sdk-hints.json").write_text("{}", encoding="utf-8")
    return run_dir


def _failing_report() -> ValidationReport:
    return ValidationReport(
        issues=[
            Issue(
                code=IssueCode.REQUIRED_INFO_MISSING,
                severity=Severity.ERROR,
                location="paths./ping.get",
                evidence="no matching source passage",
                suggested_fix="re-read the source and fill the missing field",
            )
        ]
    )


def _score_json(score: int) -> str:
    return ScoreReport(
        status=ScoreStatus.PASS,
        score=score,
        profile=ScoreProfile.CI,
        min_score=0,
        category_scores={},
    ).model_dump_json(indent=2)
