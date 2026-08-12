from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.manifest.models import LocalSource, Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.source_quality.assess import assess_source_quality
from loop_apidoc.source_quality.loader import load_assessment_reports
from loop_apidoc.source_quality.models import (
    FindingSeverity,
    QualityObservation,
    QualityVerdict,
    SourceDiffReport,
)
from loop_apidoc.source_quality.report import write_reports
from loop_apidoc.source_risk.inspect import source_binding_digest
from loop_apidoc.source_risk.models import RiskVerdict, SourceRiskReport


def _manifest(*, supported: bool = True) -> Manifest:
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)
    return Manifest(
        sources_root="./sources",
        generated_at=now,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=12,
                sha256="abc",
                scanned_at=now,
                supported=supported,
                status=ProcessingStatus.PENDING if supported else ProcessingStatus.UNSUPPORTED,
            )
        ],
    )


def _risk(manifest: Manifest) -> SourceRiskReport:
    return SourceRiskReport(
        schema_version="1",
        ruleset_version="1",
        max_bytes=5 * 1024 * 1024,
        manifest_sha256="a" * 64,
        source_binding_digest=source_binding_digest(manifest),
        verdict=RiskVerdict.PASS,
    )


def test_no_supported_source_rejects() -> None:
    manifest = _manifest(supported=False)
    report = assess_source_quality(
        manifest=manifest,
        source_set="v2",
        observations=[],
        base_report=None,
        source_risk=_risk(manifest),
    )

    assert report.verdict is QualityVerdict.REJECT
    assert report.blocker_count == 1


def test_warning_observation_allows_progress() -> None:
    manifest = _manifest()
    report = assess_source_quality(
        manifest=manifest,
        source_set="v2",
        observations=[
            QualityObservation(
                source="manual.md", locator="Overview", category="examples_missing",
                evidence="No example is supplied.", severity=FindingSeverity.WARNING,
                required_supplement="Provide an example.",
                acceptance_criteria="The example identifies its endpoint.",
            )
        ],
        base_report=None,
        source_risk=_risk(manifest),
    )

    assert report.verdict is QualityVerdict.PASS
    assert report.warning_count == 1


def test_blocker_report_round_trips_with_derived_required_source_refs(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    report = assess_source_quality(
        manifest=manifest,
        source_set="v2",
        observations=[
            QualityObservation(
                source="manual.md",
                locator="GET /ping",
                category="missing_response_contract",
                evidence="The response schema is omitted.",
                severity=FindingSeverity.BLOCKER,
                required_supplement="Provide the response schema.",
                acceptance_criteria="The documented response fields are cited.",
                required_source_refs=[
                    "https://docs.example.com/response",
                    "https://docs.example.com/errors",
                ],
            ),
            QualityObservation(
                source="manual.md",
                locator="Errors",
                category="missing_error_semantics",
                evidence="The error behavior is omitted.",
                severity=FindingSeverity.BLOCKER,
                required_supplement="Provide error behavior.",
                acceptance_criteria="The documented error semantics are cited.",
                required_source_refs=[
                    "https://docs.example.com/errors",
                    "https://docs.example.com/retries",
                ],
            ),
        ],
        base_report=None,
        source_risk=_risk(manifest),
    )
    output = tmp_path / "source-quality"
    write_reports(report, SourceDiffReport(), output)

    loaded_report, loaded_diff = load_assessment_reports(output)

    assert report.verdict is QualityVerdict.REJECT
    assert report.required_source_refs == [
        "https://docs.example.com/response",
        "https://docs.example.com/errors",
        "https://docs.example.com/retries",
    ]
    assert loaded_report.model_dump(mode="json") == report.model_dump(mode="json")
    assert loaded_diff.model_dump(mode="json") == {"entries": []}
