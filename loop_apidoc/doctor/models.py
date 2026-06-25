from __future__ import annotations

from pydantic import BaseModel


class CheckResult(BaseModel):
    name: str
    ok: bool
    detail: str
    remedy: str | None = None
    required: bool = True


class DoctorReport(BaseModel):
    checks: list[CheckResult]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks if check.required)
