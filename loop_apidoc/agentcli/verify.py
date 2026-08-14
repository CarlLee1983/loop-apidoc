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
from loop_apidoc.focus.gate import falsified_expectations, focus_evidence_references
from loop_apidoc.focus.loader import load_focus_package
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
    focus_file: Path | None = None,
) -> list[str]:
    """回傳所有違規(空 list = 乾淨)。硬 schema 錯誤由
    `load_extraction_inputs` / `load_focus_package` 拋出,不在此收斂。"""
    inventory, endpoint_texts, integration = load_extraction_inputs(extraction_dir)
    focus = (
        load_focus_package(focus_file, extraction_dir)
        if focus_file is not None else None
    )
    manifest = build_manifest(
        sources_root=sources_root, urls=urls or [],
        generated_at=generated_at, excludes=excludes)
    facts = collect_facts(sources_root, manifest)
    endpoints = named_endpoints(extraction_dir, endpoint_texts)
    violations = check_extraction(
        inventory, endpoints, integration, manifest, facts, focus)
    violations += verify_extraction_evidence(
        inventory, endpoints, integration, manifest, facts, generated_at,
        extra_references=focus_evidence_references(focus),
    )
    if not violations:
        extraction = build_extraction_from_files(inventory, endpoint_texts, store=None)
        plan = build_normalization_plan(extraction, manifest)
        contract = build_integration_contract(integration, plan, manifest)
        plan = plan.model_copy(update={"integration": contract})
        violations += verify_evidence_claim_paths(plan)
    return violations


def preview_falsified_expectations(
    *, extraction_dir: Path, focus_file: Path
) -> list[str]:
    """哪些 Expectation Directive 落空 —— 給 `verify-extraction` 當預告用。

    與 `verify_extraction_dir` 分開,是為了讓後者的回傳維持「違規字串清單」這個
    單一意義:預告不是違規,混進同一個 list 就會被呼叫端當成該擋的東西。
    """
    return falsified_expectations(load_focus_package(focus_file, extraction_dir))
