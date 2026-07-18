from __future__ import annotations

import json
import os
from pathlib import Path

from loop_apidoc import __version__
from loop_apidoc.run.models import Toolchain

# agent 產出的擷取 JSON schema(inventory / endpoints / integration)的契約版本。
# 只要該 schema 有不相容或語意上的變動就 +1,讓舊 run 的產物可被歸因。
EXTRACTION_CONTRACT_VERSION = "1"

_REPO_ROOT = Path(__file__).resolve().parents[2]


def read_skill_version(plugin_root: Path) -> str | None:
    """讀 plugin manifest 的 version;讀不到或格式不符一律回 None,絕不臆測。"""
    manifest = plugin_root / ".claude-plugin" / "plugin.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = payload.get("version") if isinstance(payload, dict) else None
    return version if isinstance(version, str) else None


def build_toolchain(*, model: str | None = None) -> Toolchain:
    """組出本次 run 的工具鏈版本紀錄。model 只接受呼叫端明確給的值。"""
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    root = Path(env_root) if env_root else _REPO_ROOT
    return Toolchain(
        cli_version=__version__,
        extraction_contract_version=EXTRACTION_CONTRACT_VERSION,
        skill_version=read_skill_version(root),
        model=model,
    )
