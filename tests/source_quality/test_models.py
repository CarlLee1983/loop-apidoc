from __future__ import annotations

import pytest
from pydantic import ValidationError

from loop_apidoc.source_quality.models import (
    FindingSeverity,
    QualityObservation,
    QualityVerdict,
    SourceQualityReport,
)


def test_reject_report_counts_blockers() -> None:
    report = SourceQualityReport(
        verdict=QualityVerdict.REJECT,
        source_set="v2",
        findings=[],
    )

    assert report.blocker_count == 0


def test_observation_requires_traceable_evidence() -> None:
    with pytest.raises(ValidationError):
        QualityObservation(
            source="supplier.pdf",
            locator="p. 12",
            category="table_unreadable",
            evidence="",
            severity=FindingSeverity.BLOCKER,
            required_supplement="Provide the original spreadsheet.",
            acceptance_criteria="The supplied file identifies its version.",
        )


def test_observation_accepts_actionable_warning() -> None:
    observation = QualityObservation(
        source="supplier.pdf",
        locator="p. 12",
        category="examples_missing",
        evidence="The endpoint table contains no payload example.",
        severity=FindingSeverity.WARNING,
        required_supplement="Provide request and response examples.",
        acceptance_criteria="Each example names the endpoint and document version.",
    )

    assert observation.severity is FindingSeverity.WARNING
