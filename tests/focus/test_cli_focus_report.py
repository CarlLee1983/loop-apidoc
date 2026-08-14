"""focus 報告:這個功能的完整稽核面。

沒有下游帶著 focus 材料(ADR 0004),所以判斷「這條指令有沒有被誠實回答」需要的
一切,都必須在這裡看得到。
"""
from __future__ import annotations

import json

from tests.focus.support import (
    assemble,
    directive,
    not_found,
    response,
    setup,
)


def _run_dir(tmp_path, res):
    return tmp_path / "runs" / json.loads(res.stdout)["run_id"]


def _report(tmp_path, res) -> dict:
    return json.loads(
        (_run_dir(tmp_path, res) / "focus" / "focus-report.json").read_text("utf-8"))


def _markdown(tmp_path, res) -> str:
    return (_run_dir(tmp_path, res) / "focus" / "focus-report.zh-TW.md").read_text("utf-8")


def test_a_focused_run_writes_both_report_forms(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[response()])

    res = assemble(tmp_path, sources, extraction, focus, "--json")
    focus_dir = _run_dir(tmp_path, res) / "focus"

    assert (focus_dir / "focus-report.json").exists()
    assert (focus_dir / "focus-report.zh-TW.md").exists()


def test_an_unfocused_run_writes_no_focus_directory(tmp_path):
    sources, extraction, _ = setup(tmp_path, responses=[response()])

    res = assemble(tmp_path, sources, extraction, None, "--json")

    assert not (_run_dir(tmp_path, res) / "focus").exists()


def test_each_directive_appears_once_with_its_declaration_and_outcome(tmp_path):
    sources, extraction, focus = setup(
        tmp_path,
        directives=[directive(), directive(id="settle", kind="coverage")],
        responses=[response(), not_found(id="settle")])

    res = assemble(tmp_path, sources, extraction, focus, "--json")
    entries = _report(tmp_path, res)["directives"]

    assert [e["id"] for e in entries] == ["ping", "settle"]
    ping = entries[0]
    assert ping["text"] == "一定要找到健康檢查端點"
    assert ping["kind"] == "expectation"
    assert ping["intent"] == "find_operation"
    assert ping["outcome"] == "satisfied"


def test_a_satisfied_entry_shows_its_anchors_and_the_exact_fragment(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[response()])

    res = assemble(tmp_path, sources, extraction, focus, "--json")
    anchor = _report(tmp_path, res)["directives"][0]["anchors"][0]

    assert anchor["value"] == "GET /ping"
    assert anchor["evidence"][0]["source"] == "manual.md"
    assert anchor["evidence"][0]["locator"]["start_line"] == 3
    assert anchor["reported_by"] == "ep0"


def test_a_not_found_entry_shows_every_source_searched(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[not_found()])

    res = assemble(tmp_path, sources, extraction, focus, "--json")
    entry = _report(tmp_path, res)["directives"][0]

    assert entry["searched_sources"] == ["manual.md"]
    assert entry["anchors"] == []


def test_the_markdown_leads_with_failed_expectations(tmp_path):
    sources, extraction, focus = setup(
        tmp_path,
        directives=[directive(id="found"), directive(id="lost")],
        responses=[response(id="found"), not_found(id="lost")])

    res = assemble(tmp_path, sources, extraction, focus, "--json")
    body = _markdown(tmp_path, res)

    assert body.index("lost") < body.index("found")


def test_the_markdown_names_the_run_and_counts_the_outcomes(tmp_path):
    sources, extraction, focus = setup(
        tmp_path,
        directives=[directive(id="found"), directive(id="lost")],
        responses=[response(id="found"), not_found(id="lost")])

    res = assemble(tmp_path, sources, extraction, focus, "--json")
    body = _markdown(tmp_path, res)

    assert "1" in body
    assert "未達成" in body


def test_no_focus_material_reaches_a_governed_or_comparable_artifact(tmp_path):
    # ADR 0004 的邊界:focus 只活在 run 目錄的 focus/ 底下。
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[not_found()])

    res = assemble(tmp_path, sources, extraction, focus, "--json")
    run_dir = _run_dir(tmp_path, res)

    # 提出者的原話是最不可能巧合出現的 focus 材料 —— 拿它當示蹤劑,
    # 而不是 "focus" 這個字(pytest 的 tmp 目錄名就帶著它)。
    tracer = "一定要找到健康檢查端點"
    allowed = {(run_dir / "focus"), (run_dir / "validation")}
    leaked = [
        path.relative_to(run_dir).as_posix()
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
        and not any(parent in allowed for parent in path.parents)
        and tracer in path.read_text("utf-8", errors="ignore")
    ]

    assert leaked == []
