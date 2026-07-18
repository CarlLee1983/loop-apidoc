"""`verify-extraction` 的薄殼:建 manifest、讀擷取目錄、跑同一個閘門。

不寫任何檔、不建立 run 目錄。`assemble` 與這裡呼叫的是同一個
`gate.check_extraction`,兩個入口不可能漂移。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from loop_apidoc.agentcli.assemble import load_extraction_inputs, named_endpoints
from loop_apidoc.agentcli.gate import check_extraction
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.source_facts.collect import collect_facts


def verify_extraction_dir(
    *,
    sources_root: Path,
    extraction_dir: Path,
    generated_at: datetime,
    urls: list[str] | None = None,
    excludes: Sequence[str] = (),
) -> list[str]:
    """回傳所有違規(空 list = 乾淨)。硬 schema 錯誤由
    `load_extraction_inputs` 拋 AssembleInputError,不在此收斂。"""
    inventory, endpoint_texts, integration = load_extraction_inputs(extraction_dir)
    manifest = build_manifest(
        sources_root=sources_root, urls=urls or [],
        generated_at=generated_at, excludes=excludes)
    return check_extraction(
        inventory, named_endpoints(extraction_dir, endpoint_texts),
        integration, manifest, collect_facts(sources_root, manifest))
