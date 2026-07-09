"""擷取輸入的邊界閘門:一個定義,兩個入口。

`assemble` 與 `verify-extraction` 都只呼叫 `check_extraction`,兩者不可能漂移。
純函式、不做檔案 I/O;呼叫端把回傳的訊息轉成 AssembleInputError。

硬 schema 錯誤(JSON 壞掉、型別錯)不在這裡——那些由
`load_extraction_inputs` 在讀檔時就 fail loudly,因為它們會讓後續檢查失去意義。
"""

from __future__ import annotations

from loop_apidoc.agentcli.cross_file import cross_file_violations
from loop_apidoc.agentcli.source_guard import check_extraction_inputs
from loop_apidoc.manifest.models import Manifest


def check_extraction(
    inventory: dict,
    endpoints: list[tuple[str, dict]],
    integration: dict | None,
    manifest: Manifest,
) -> list[str]:
    """一次列出所有違規(path / source / 跨檔),讓 agent 一次改寫即可。"""
    return check_extraction_inputs(
        inventory, endpoints, integration, manifest
    ) + cross_file_violations(inventory, endpoints)
