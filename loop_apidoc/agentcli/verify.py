"""`verify-extraction` 的薄殼:建 manifest、讀擷取目錄、跑同一個閘門。

不寫任何檔、不建立 run 目錄。`assemble` 與這裡呼叫的是同一個
`gate.check_extraction`,兩個入口不可能漂移。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from loop_apidoc.agentcli.assemble import (
    build_extraction_from_files,
    load_extraction_inputs,
    named_endpoints,
)
from loop_apidoc.agentcli.evidence import (
    verify_evidence_claim_paths,
    verify_extraction_evidence,
)
from loop_apidoc.agentcli.gate import check_extraction
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.plan.integration import build_integration_contract
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
    facts = collect_facts(sources_root, manifest)
    endpoints = named_endpoints(extraction_dir, endpoint_texts)
    violations = check_extraction(inventory, endpoints, integration, manifest, facts)
    violations += verify_extraction_evidence(
        inventory, endpoints, integration, manifest, facts, generated_at
    )
    if not violations:
        extraction = build_extraction_from_files(inventory, endpoint_texts, store=None)
        plan = build_normalization_plan(extraction, manifest)
        contract = build_integration_contract(integration, plan, manifest)
        plan = plan.model_copy(update={"integration": contract})
        violations += verify_evidence_claim_paths(plan)
    return violations
