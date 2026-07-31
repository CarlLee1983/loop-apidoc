from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import LocalSource, Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.source_quality.assess import assess_source_quality
from loop_apidoc.source_quality.models import FindingSeverity, QualityObservation, QualityVerdict
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
