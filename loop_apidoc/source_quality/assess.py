from __future__ import annotations

from loop_apidoc.manifest.models import Manifest, ProcessingStatus
from loop_apidoc.source_quality.models import (
    FindingSeverity,
    QualityFinding,
    QualityObservation,
    QualityVerdict,
    SourceQualityReport,
)


def _finding(identifier: int, observation: QualityObservation) -> QualityFinding:
    return QualityFinding(id=f"SQ-{identifier:03d}", **observation.model_dump())


def assess_source_quality(
    *,
    manifest: Manifest,
    source_set: str,
    observations: list[QualityObservation],
    base_report: SourceQualityReport | None,
) -> SourceQualityReport:
    findings: list[QualityFinding] = []
    usable = [
        source
        for source in manifest.local_sources
        if source.supported and source.status is ProcessingStatus.PENDING
    ]
    if not usable:
        findings.append(
            _finding(
                1,
                QualityObservation(
                    source="manifest.json",
                    locator="local_sources",
                    category="no_usable_source",
                    evidence="No supported pending local source is available.",
                    severity=FindingSeverity.BLOCKER,
                    required_supplement="Provide at least one readable supported source.",
                    acceptance_criteria="The source appears as supported and pending in manifest.json.",
                ),
            )
        )
    findings.extend(_finding(index, observation) for index, observation in enumerate(observations, len(findings) + 1))
    verdict = (
        QualityVerdict.REJECT
        if any(finding.is_blocker for finding in findings)
        else QualityVerdict.PASS
    )
    return SourceQualityReport(
        verdict=verdict,
        source_set=source_set,
        base_source_set=base_report.source_set if base_report else None,
        findings=findings,
    )
