"""Full-run orchestration and correction loop (spec §3.2, §8, §10)."""

from loop_apidoc.run.models import (
    CorrectionCategory,
    CorrectionOutcome,
    RunResult,
    RunStatus,
)
from loop_apidoc.run.runid import make_run_id

__all__ = [
    "CorrectionCategory",
    "CorrectionOutcome",
    "RunResult",
    "RunStatus",
    "make_run_id",
]
