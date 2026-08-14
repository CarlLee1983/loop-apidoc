"""focus 報告 —— 這個套件的寫入出口。

沒有任何下游產物帶著 focus 材料(ADR 0004),所以判斷「這條指令有沒有被誠實
回答」需要的一切都必須在這裡看得到:提出者的原話、結局、錨點釘在哪一段來源、
以及 `not_found` 查過哪些來源。

Markdown 是給人讀的那一份,所以它把未達成的斷言排在最前面 —— 開啟報告的人在
找的就是那個。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loop_apidoc.focus.models import FocusDirective, FocusPackage, FocusResponse

_KIND_LABEL = {"expectation": "斷言", "coverage": "範圍"}


def build_report(focus: FocusPackage) -> dict[str, Any]:
    """依 focus.json 的宣告順序,逐條列出結局。純函式。"""
    by_id = {response.id: response for response in focus.responses}
    directives = [
        _entry(directive, by_id.get(directive.id))
        for directive in focus.directives
    ]
    return {
        "version": 1,
        "summary": {
            "total": len(directives),
            "satisfied": sum(1 for e in directives if e["outcome"] == "satisfied"),
            "unmet_expectations": sum(
                1 for e in directives
                if e["outcome"] == "not_found" and e["kind"] == "expectation"
            ),
            "unmet_coverage": sum(
                1 for e in directives
                if e["outcome"] == "not_found" and e["kind"] == "coverage"
            ),
        },
        "directives": directives,
    }


def write_reports(focus: FocusPackage, run_dir: Path) -> Path:
    """寫入 `<run-dir>/focus/`。這是本套件唯一的寫入點。"""
    report = build_report(focus)
    out = run_dir / "focus"
    out.mkdir(parents=True, exist_ok=True)
    (out / "focus-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "focus-report.zh-TW.md").write_text(
        render_markdown(report), encoding="utf-8")
    return out


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 擷取重點指令報告",
        "",
        f"共 {summary['total']} 條指令:{summary['satisfied']} 條達成、"
        f"{summary['unmet_expectations']} 條斷言未達成、"
        f"{summary['unmet_coverage']} 條範圍查無記載。",
        "",
        "未達成的斷言代表**你主張來源記載了它,而擷取沒找到**。這不是要靠改寫答案"
        "消掉的東西 —— 先確認是不是漏看,若供應商確實未記載,該補的是來源。",
        "",
    ]
    unmet = [e for e in report["directives"]
             if e["outcome"] == "not_found" and e["kind"] == "expectation"]
    rest = [e for e in report["directives"] if e not in unmet]
    for heading, entries in (("未達成的斷言", unmet), ("其餘指令", rest)):
        if not entries:
            continue
        lines += [f"## {heading}", ""]
        for entry in entries:
            lines += _entry_markdown(entry)
    return "\n".join(lines).rstrip() + "\n"


def _entry_markdown(entry: dict[str, Any]) -> list[str]:
    kind = _KIND_LABEL.get(entry["kind"], entry["kind"])
    lines = [
        f"### `{entry['id']}` — {kind}／{entry['intent']}",
        "",
        f"> {entry['text']}",
        "",
        f"結局:**{entry['outcome']}**"
        + (f"(由 {entry['reported_by']} 回報)" if entry.get("reported_by") else ""),
        "",
    ]
    if entry["rationale"]:
        lines += [f"提出理由:{entry['rationale']}", ""]
    if entry["anchors"]:
        lines += ["| 錨點 | 型別 | 來源片段 |", "| --- | --- | --- |"]
        for anchor in entry["anchors"]:
            fragments = "；".join(_fragment_label(e) for e in anchor["evidence"])
            lines.append(
                f"| `{anchor['value']}` | {anchor['type']} | {fragments} |")
        lines.append("")
    if entry["searched_sources"]:
        lines += [
            "已查來源:" + "、".join(f"`{s}`" for s in entry["searched_sources"]),
            "",
        ]
    return lines


def _fragment_label(reference: dict[str, Any]) -> str:
    locator = reference.get("locator") or {}
    start = locator.get("start_line")
    end = locator.get("end_line")
    where = f" L{start}-{end}" if start is not None else ""
    return f"`{reference['source']}{where}`"


def _entry(
    directive: FocusDirective, response: FocusResponse | None
) -> dict[str, Any]:
    return {
        "id": directive.id,
        "kind": directive.kind,
        "intent": directive.intent,
        "text": directive.text,
        "rationale": directive.rationale,
        "outcome": response.outcome if response else None,
        "reported_by": response.reported_by if response else None,
        "anchors": [
            {
                "type": anchor.type,
                "value": anchor.value,
                "reported_by": response.reported_by,
                "evidence": [
                    reference.model_dump(mode="json")
                    for reference in anchor.evidence
                ],
            }
            for anchor in (response.anchors if response else [])
        ],
        "searched_sources": list(response.searched_sources) if response else [],
    }
