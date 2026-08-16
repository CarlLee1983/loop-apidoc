"""`verify-extraction` 的薄殼:建 manifest、讀擷取目錄、跑同一個閘門。

不寫任何檔、不建立 run 目錄。`assemble` 與這裡呼叫的是同一個
`gate.check_extraction`,兩個入口不可能漂移。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple
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
from loop_apidoc.agentcli.identity import extraction_identities
from loop_apidoc.focus.gate import falsified_expectations, focus_evidence_references
from loop_apidoc.focus.loader import load_focus_package
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.plan.integration import build_integration_contract
from loop_apidoc.source_facts.collect import collect_facts
from loop_apidoc.agentcli.fact_coverage import build_fact_coverage
from loop_apidoc.validate.fact_coverage import unscanned_sources
from loop_apidoc.validate.focus import omitted_error_codes


class VerifyOutcome(NamedTuple):
    """一次 `verify-extraction` 的兩種輸出,分開命名。

    `violations` 是該擋的東西(exit 2);`unscanned` 是預告 —— 語意完整性閘門對
    哪些來源不會有作用。混進同一個 list 就會被呼叫端當成該擋的東西。
    """

    violations: list[str]
    unscanned: list[str]


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
    return verify_extraction(
        sources_root=sources_root,
        extraction_dir=extraction_dir,
        generated_at=generated_at,
        urls=urls,
        excludes=excludes,
        focus_file=focus_file,
    ).violations


def verify_extraction(
    *,
    sources_root: Path,
    extraction_dir: Path,
    generated_at: datetime,
    urls: list[str] | None = None,
    excludes: Sequence[str] = (),
    focus_file: Path | None = None,
) -> VerifyOutcome:
    """閘門 + 事實涵蓋預告,共用同一次來源掃描。

    CLI 走這個入口,所以一次 `verify-extraction` 只掃一遍來源目錄:預告用的
    manifest 與 `FactIndex` 就是閘門剛用過的那兩份,兩者不可能給出不一致的判斷。
    """
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
    coverage = build_fact_coverage(
        manifest, facts, extraction_identities(inventory, endpoints))
    return VerifyOutcome(violations=violations, unscanned=_forecast(coverage))


def _forecast(coverage) -> list[str]:
    """把投影寫成人可讀的一行一份來源。"""
    lines: list[str] = []
    for source, entry in unscanned_sources(coverage):
        if entry.facts == 0 and entry.unclosed_fence_line is not None:
            lines.append(
                f"{source}:第 {entry.unclosed_fence_line} 行的圍籬未關閉,"
                "其後的內容全部沒被讀到"
            )
        elif entry.facts == 0:
            lines.append(f"{source}:掃出 0 筆端點事實")
        else:
            lines.append(
                f"{source}:{entry.facts} 筆事實無一對上 extraction 的端點")
    return lines


def preview_falsified_expectations(
    *, extraction_dir: Path, focus_file: Path
) -> list[str]:
    """哪些 Expectation Directive 落空 —— 給 `verify-extraction` 當預告用。

    與 `verify_extraction_dir` 分開,是為了讓後者的回傳維持「違規字串清單」這個
    單一意義:預告不是違規,混進同一個 list 就會被呼叫端當成該擋的東西。
    """
    return falsified_expectations(load_focus_package(focus_file, extraction_dir))


def preview_error_code_shortfall(
    *,
    sources_root: Path,
    extraction_dir: Path,
    generated_at: datetime,
    focus_file: Path,
    excludes: Sequence[str] = (),
) -> list[str]:
    """哪些窮盡型指令報得比記載錯誤碼下界少 —— 同樣是預告,不是違規。

    短少只在 `assemble` 才成為驗證問題,因為只有它跑 validate。少了這段預告,
    agent 要等整趟 assemble 跑完才知道該回頭去讀錯誤碼表。

    重建一次 manifest 與事實索引,而不是把它們從 `verify_extraction_dir` 傳出來:
    那個函式的回傳值只有一個意義(該擋的違規字串),把預告需要的東西塞進去會
    毀掉它。多掃一次來源目錄的代價,遠小於那個意義被稀釋。

    刻意不帶 URL:`collect_facts` 只讀 `manifest.local_sources`,所以下界完全
    不受 URL 來源影響,而帶了就得為一段預告把每個 URL 重新連網探測一次。這條
    不變式由 `tests/source_facts/test_collect.py` 釘住。
    """
    focus = load_focus_package(focus_file, extraction_dir)
    manifest = build_manifest(
        sources_root=sources_root, urls=[],
        generated_at=generated_at, excludes=excludes)
    floor = collect_facts(sources_root, manifest).documented_error_codes()
    return [
        f"{directive.id}:{'、'.join(omitted)}"
        for directive, omitted in omitted_error_codes(focus, floor)
    ]
