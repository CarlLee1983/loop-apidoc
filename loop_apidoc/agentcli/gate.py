"""擷取輸入的邊界閘門:一個定義,兩個入口。

`assemble` 與 `verify-extraction` 都只呼叫 `check_extraction`,兩者不可能漂移。
純函式、不做檔案 I/O;呼叫端把回傳的訊息轉成 AssembleInputError。
來源事實由呼叫端先用 `collect_facts` 讀好再傳進來,好維持這裡的純度。

硬 schema 錯誤(JSON 壞掉、型別錯)不在這裡——那些由
`load_extraction_inputs` 在讀檔時就 fail loudly,因為它們會讓後續檢查失去意義。
"""

from __future__ import annotations

from loop_apidoc.agentcli.cross_file import cross_file_violations
from loop_apidoc.agentcli.source_guard import check_extraction_inputs
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.source_facts.deferral import deferral_violations
from loop_apidoc.source_facts.gate import source_fact_violations
from loop_apidoc.source_facts.models import FactIndex


def check_extraction(
    inventory: dict,
    endpoints: list[tuple[str, dict]],
    integration: dict | None,
    manifest: Manifest,
    facts: FactIndex | None = None,
) -> list[str]:
    """一次列出所有違規(path / source / 跨檔 / 來源事實),讓 agent 一次改寫即可。"""
    return (
        check_extraction_inputs(inventory, endpoints, integration, manifest)
        + cross_file_violations(inventory, endpoints)
        + source_fact_violations(facts or FactIndex(), endpoints, inventory)
        + deferral_violations(endpoints)
    )
