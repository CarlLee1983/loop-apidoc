from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.source_risk.inspect import (
    RULESET_VERSION,
    SCHEMA_VERSION,
    SourceRiskInputError,
    inspect_source_risks,
    source_binding_digest,
)
from loop_apidoc.source_risk.models import RiskVerdict, SourceRiskReport


def verify_source_risk_report(
    report: SourceRiskReport,
    *,
    manifest: Manifest,
    sources_root: Path,
    manifest_sha256: str | None = None,
) -> None:
    if report.schema_version != SCHEMA_VERSION:
        raise SourceRiskInputError("source-risk report schema version is stale")
    if report.ruleset_version != RULESET_VERSION:
        raise SourceRiskInputError("source-risk report ruleset version is stale")
    if report.source_binding_digest != source_binding_digest(manifest):
        raise SourceRiskInputError("source-risk report source binding mismatch")
    if manifest_sha256 is not None and report.manifest_sha256 != manifest_sha256:
        raise SourceRiskInputError("source-risk report manifest digest mismatch")
    expected = inspect_source_risks(
        sources_root=sources_root,
        manifest=manifest,
        manifest_sha256=report.manifest_sha256,
        max_bytes=report.max_bytes,
    )
    if report != expected:
        raise SourceRiskInputError(
            "source-risk report does not match deterministic inspection"
        )
    if report.verdict is not RiskVerdict.PASS:
        raise SourceRiskInputError("source-risk report verdict is reject")


def load_verified_source_risk_report(
    path: Path,
    *,
    manifest: Manifest,
    sources_root: Path,
    manifest_sha256: str | None = None,
) -> SourceRiskReport:
    report_path = path / "source-risk-report.json"
    try:
        report = SourceRiskReport.model_validate_json(
            report_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise SourceRiskInputError(
            f"invalid source-risk report: {report_path}"
        ) from exc
    verify_source_risk_report(
        report,
        manifest=manifest,
        sources_root=sources_root,
        manifest_sha256=manifest_sha256,
    )
    return report
