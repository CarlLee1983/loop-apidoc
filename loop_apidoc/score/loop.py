from __future__ import annotations

from enum import Enum

from loop_apidoc.score.models import ScoreFinding
from loop_apidoc.validate.models import IssueCode, Severity


class LoopVerdict(str, Enum):
    CONVERGED = "converged"
    PLATEAU = "plateau"
    EXHAUSTED = "exhausted"
    CONTINUE = "continue"


# Findings an agent re-read can plausibly resolve — only at error severity.
# Everything else (every warning is source-silent; SOURCE_CONFLICT and
# UNSUPPORTED_ASSERTION are always fail-closed) is irreducible and must never be
# auto-fixed to raise the score.
_REDUCIBLE_ERROR_CODES: frozenset[str] = frozenset({
    IssueCode.OPENAPI_INVALID.value,
    IssueCode.OUTPUT_MISMATCH.value,
    IssueCode.REQUIRED_INFO_MISSING.value,
    IssueCode.SOURCE_UNVERIFIED.value,
})


def _is_reducible(finding: ScoreFinding) -> bool:
    if finding.severity != Severity.ERROR.value:
        return False
    return finding.code in _REDUCIBLE_ERROR_CODES


def classify_findings(
    findings: list[ScoreFinding],
) -> tuple[list[ScoreFinding], list[ScoreFinding]]:
    """Split findings into (reducible, irreducible), preserving order."""
    reducible = [f for f in findings if _is_reducible(f)]
    irreducible = [f for f in findings if not _is_reducible(f)]
    return reducible, irreducible
