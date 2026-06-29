from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IssueCode(str, Enum):
    SOURCE_UNVERIFIED = "SOURCE_UNVERIFIED"
    REQUIRED_INFO_MISSING = "REQUIRED_INFO_MISSING"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    OPENAPI_INVALID = "OPENAPI_INVALID"
    OUTPUT_MISMATCH = "OUTPUT_MISMATCH"
    UNSUPPORTED_ASSERTION = "UNSUPPORTED_ASSERTION"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class Issue(BaseModel):
    code: IssueCode
    severity: Severity
    location: str
    evidence: str
    suggested_fix: str
    auto_fixable: bool = False
    # 選填的結構化修正路由(供 agent 校正迴圈直接定位要改哪個檔/哪個欄位,
    # 不必再從自由文字 location 推斷;validator 僅在映射確定時填寫,否則維持 None)。
    target_file: str | None = None  # "inventory.json" | "endpoints/epN.json" | "integration.json"
    field_path: str | None = None  # 進入該檔的 JSON-pointer 式路徑
    requery_scope: str | None = None  # 有界的重讀提示(來源段落/endpoint ref/契約區塊)


class ValidationReport(BaseModel):
    issues: list[Issue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity is Severity.ERROR for i in self.issues)

    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]
