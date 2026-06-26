from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.validate.models import ValidationReport


class RunStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    EARLY_STOPPED = "early-stopped"
    BLOCKED = "blocked"


class CorrectionCategory(str, Enum):
    AUTO_FIX = "auto-fix"
    RE_QUERY = "re-query"
    UNFIXABLE = "unfixable"


class CorrectionOutcome(BaseModel):
    plan: NormalizationPlan
    result: GenerateResult
    report: ValidationReport
    rounds: int
    status: RunStatus


class RunResult(BaseModel):
    run_id: str
    run_dir: str
    report: ValidationReport
    rounds: int
    status: RunStatus

    @property
    def ok(self) -> bool:
        return self.status is RunStatus.PASSED
