"""Score reports for completed loop-apidoc run directories."""

from loop_apidoc.score.evaluate import evaluate_score
from loop_apidoc.score.loader import load_score_inputs
from loop_apidoc.score.loop import (
    LoopReport,
    LoopVerdict,
    classify_findings,
    loop_verdict,
)
from loop_apidoc.score.models import (
    CATEGORY_WEIGHTS,
    DEFAULT_MIN_SCORES,
    ScoreCategory,
    ScoreFinding,
    ScoreInputError,
    ScoreInputs,
    ScoreProfile,
    ScoreReport,
    ScoreStatus,
    resolved_min_score,
)
from loop_apidoc.score.report import render_markdown, write_reports

__all__ = [
    "CATEGORY_WEIGHTS",
    "DEFAULT_MIN_SCORES",
    "LoopReport",
    "LoopVerdict",
    "ScoreCategory",
    "ScoreFinding",
    "ScoreInputError",
    "ScoreInputs",
    "ScoreProfile",
    "ScoreReport",
    "ScoreStatus",
    "classify_findings",
    "evaluate_score",
    "load_score_inputs",
    "loop_verdict",
    "render_markdown",
    "resolved_min_score",
    "write_reports",
]
