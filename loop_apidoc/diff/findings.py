"""Finding primitives shared by the diff comparison modules."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from loop_apidoc.diff.models import DiffFinding, DiffImpact

_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
_IMPACT_ORDER = {
    DiffImpact.BREAKING: 0,
    DiffImpact.ADDITIVE: 1,
    DiffImpact.CHANGED: 2,
    DiffImpact.SOURCE_ONLY: 3,
}
_SUMMARY_KEYS = [impact.value for impact in DiffImpact]


def _finding(
    impact: DiffImpact,
    area: str,
    location: str,
    summary: str,
    before: Any | None = None,
    after: Any | None = None,
) -> DiffFinding:
    return DiffFinding(
        impact=impact,
        area=area,
        location=location,
        summary=summary,
        before=before,
        after=after,
    )


def _sorted_findings(findings: Iterable[DiffFinding]) -> list[DiffFinding]:
    return sorted(
        findings,
        key=lambda f: (_IMPACT_ORDER[f.impact], f.area, f.location, f.summary),
    )


def _summary(findings: list[DiffFinding]) -> dict[str, int]:
    counts = {key: 0 for key in _SUMMARY_KEYS}
    for finding in findings:
        counts[finding.impact.value] += 1
    return counts

