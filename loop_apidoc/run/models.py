from __future__ import annotations

from datetime import datetime
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


class Toolchain(BaseModel):
    """產生這次 run 的工具鏈版本;解析不到的欄位留 null,不臆測。"""

    cli_version: str
    extraction_contract_version: str
    skill_version: str | None = None
    model: str | None = None


class RunDescriptor(BaseModel):
    """寫入 run 目錄的 run.json:讓回歸能單憑產物歸因到版本。"""

    run_id: str
    status: RunStatus
    generated_at: datetime
    toolchain: Toolchain


class RunResult(BaseModel):
    run_id: str
    run_dir: str
    report: ValidationReport
    rounds: int
    status: RunStatus
    toolchain: Toolchain | None = None

    @property
    def ok(self) -> bool:
        return self.status is RunStatus.PASSED
