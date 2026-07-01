from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

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


class LoopReport(BaseModel):
    verdict: LoopVerdict
    target: int = Field(ge=0, le=100)
    prev_score: int | None = Field(default=None, ge=0, le=100)
    curr_score: int = Field(ge=0, le=100)
    round_index: int = Field(ge=1)
    max_rounds: int = Field(ge=1)
    actionable: list[ScoreFinding] = Field(default_factory=list)
    irreducible: list[ScoreFinding] = Field(default_factory=list)


def loop_verdict(
    *,
    prev_score: int | None,
    curr_score: int,
    target: int,
    round_index: int,
    max_rounds: int,
    findings: list[ScoreFinding],
) -> LoopReport:
    """Decide whether the agent should keep correcting toward the score target.

    Precedence (first match wins): converged (curr>=target) -> exhausted
    (round>=max) -> plateau (no reducible findings) -> plateau (no improvement)
    -> continue. Pure: no I/O.
    """
    if not 0 <= curr_score <= 100:
        raise ValueError(f"curr_score out of range 0-100: {curr_score}")
    if not 0 <= target <= 100:
        raise ValueError(f"target out of range 0-100: {target}")
    if prev_score is not None and not 0 <= prev_score <= 100:
        raise ValueError(f"prev_score out of range 0-100: {prev_score}")
    if round_index < 1:
        raise ValueError(f"round_index must be >= 1: {round_index}")
    if max_rounds < 1:
        raise ValueError(f"max_rounds must be >= 1: {max_rounds}")

    reducible, irreducible = classify_findings(findings)

    if curr_score >= target:
        verdict = LoopVerdict.CONVERGED
    elif round_index >= max_rounds:
        verdict = LoopVerdict.EXHAUSTED
    elif not reducible:
        verdict = LoopVerdict.PLATEAU
    elif prev_score is not None and curr_score <= prev_score:
        verdict = LoopVerdict.PLATEAU
    else:
        verdict = LoopVerdict.CONTINUE

    return LoopReport(
        verdict=verdict,
        target=target,
        prev_score=prev_score,
        curr_score=curr_score,
        round_index=round_index,
        max_rounds=max_rounds,
        actionable=reducible,
        irreducible=irreducible,
    )
