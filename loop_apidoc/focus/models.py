"""擷取重點指令與應答的型別契約。

兩個分類欄位各管一件事,互不干涉:`kind` 是 severity 的唯一來源,`intent` 是
錨點型別的唯一來源。沒有第三個欄位可以覆寫任何一個 —— 想要不阻斷的結局,寫
成 Coverage Directive,而不是帶降級旗標的 Expectation Directive。

應答只有 `satisfied` 與 `not_found` 兩種結局。刻意沒有「不適用」:一條 directive
適不適用是提出者的判斷,給 agent 這顆按鈕等於給它一個永遠能按的脫身鍵。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from loop_apidoc.extraction.evidence import ExtractionEvidenceReference

DirectiveKind = Literal["coverage", "expectation"]
# 每新增一種 intent 就要同時交出它的確定性錨點解析器,所以這個列舉是隨解析器
# 一起長出來的,不是先宣告後補實作。
DirectiveIntent = Literal["find_operation"]
# 錨點詞彙本身已經定案(operation / field / error_code),即使解析器還沒到齊 ——
# 型別留在這裡,intent↔type 的相符檢查才報得出「這個 intent 要的是哪一種錨點」。
AnchorType = Literal["operation", "field", "error_code"]

_INTENT_ANCHOR: dict[str, str] = {"find_operation": "operation"}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FocusDirective(_Strict):
    id: str
    kind: DirectiveKind
    intent: DirectiveIntent
    text: str
    rationale: str | None = None

    @field_validator("id", "text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不可為空白")
        return value

    @property
    def anchor_type(self) -> str:
        return _INTENT_ANCHOR[self.intent]


class FocusFile(_Strict):
    version: Literal[1]
    directives: list[FocusDirective]

    @model_validator(mode="after")
    def _ids_are_unique(self) -> FocusFile:
        seen: set[str] = set()
        for directive in self.directives:
            if directive.id in seen:
                raise ValueError(f"directive id 重複:{directive.id!r}")
            seen.add(directive.id)
        return self


class FocusAnchor(_Strict):
    type: AnchorType
    value: str
    # 至少一筆 v1 exact evidence:提出者斷言了某樣東西存在,回報「找到了」時就
    # 該指得出是哪一行。filename-only 引用正是最容易唬的形式。
    evidence: list[ExtractionEvidenceReference]

    @field_validator("value")
    @classmethod
    def _value_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("錨點值不可為空白")
        return value

    @field_validator("evidence")
    @classmethod
    def _evidence_is_present(
        cls, value: list[ExtractionEvidenceReference]
    ) -> list[ExtractionEvidenceReference]:
        if not value:
            raise ValueError("satisfied 錨點必須帶至少一筆 v1 exact evidence")
        return value


class FocusResponse(_Strict):
    id: str
    outcome: Literal["satisfied", "not_found"]
    reported_by: str
    anchors: list[FocusAnchor] = []
    searched_sources: list[str] = []


class FocusResponseFile(_Strict):
    version: Literal[1]
    responses: list[FocusResponse]

    @model_validator(mode="after")
    def _ids_are_unique(self) -> FocusResponseFile:
        seen: set[str] = set()
        for response in self.responses:
            if response.id in seen:
                raise ValueError(f"response id 重複:{response.id!r}")
            seen.add(response.id)
        return self


class FocusPackage(_Strict):
    """一次 run 的完整 focus 輸入:提出者的指令與 agent 的應答。"""

    directives: list[FocusDirective]
    responses: list[FocusResponse]
