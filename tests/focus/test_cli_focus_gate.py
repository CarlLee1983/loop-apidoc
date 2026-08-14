"""`--focus` 的結構閘門,在兩個 CLI 入口上驗。

語意結局(Expectation 落空)不在這裡 —— 那走 ValidationReport,見
`test_cli_focus_outcomes.py`。這裡只驗「應答的形狀對不對、錨點指得到東西、
證據真的釘在來源上」。
"""
from __future__ import annotations

from tests.focus.support import (
    assemble as _assemble,
    directive as _directive,
    evidence as _evidence,
    response as _response,
    setup as _setup,
    verify as _verify,
)


# --- the flag is optional -------------------------------------------------

def test_without_the_flag_a_stray_response_file_is_ignored(tmp_path):
    sources, extraction, _ = _setup(tmp_path, responses=[_response(id="nope")])

    res = _verify(sources, extraction)

    assert res.exit_code == 0, res.output


def test_a_satisfied_operation_anchor_passes(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive()], responses=[_response()])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 0, res.output


# --- file shape -----------------------------------------------------------

def test_a_malformed_focus_file_is_rejected(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, focus_body="{ nope", responses=[_response()])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "focus" in res.output.lower()


def test_duplicate_directive_ids_are_rejected(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive(), _directive()],
        responses=[_response()])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "ping" in res.output


def test_an_unknown_outcome_is_rejected(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive()],
        responses=[{"id": "ping", "outcome": "not_applicable",
                    "reported_by": "ep0"}])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "outcome" in res.output


def test_a_missing_response_file_is_rejected(tmp_path):
    sources, extraction, focus = _setup(tmp_path, directives=[_directive()])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "focus-response.json" in res.output


# --- directive/response correspondence ------------------------------------

def test_an_unanswered_directive_is_rejected(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive(), _directive(id="errors")],
        responses=[_response()])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "errors" in res.output


def test_a_response_to_no_declared_directive_is_rejected(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive()],
        responses=[_response(), _response(id="ghost")])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "ghost" in res.output


# --- anchor resolution ----------------------------------------------------

def test_an_anchor_naming_an_absent_operation_is_rejected(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive()],
        responses=[_response(anchors=[
            {"type": "operation", "value": "DELETE /ping",
             "evidence": [_evidence()]}])])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "DELETE /ping" in res.output


def test_a_null_path_webhook_resolves_on_method_and_summary(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive(id="settle")],
        responses=[_response(id="settle", anchors=[
            {"type": "operation", "value": "POST (webhook) Settle callback",
             "evidence": [_evidence(line=5, text="Settle callback")]}])])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 0, res.output


def test_a_satisfied_response_without_an_anchor_is_rejected(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive()],
        responses=[_response(anchors=[])])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "ping" in res.output


def test_an_anchor_type_foreign_to_the_intent_is_rejected(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive()],
        responses=[_response(anchors=[
            {"type": "error_code", "value": "1001",
             "evidence": [_evidence()]}])])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "find_operation" in res.output


# --- evidence -------------------------------------------------------------

def test_an_anchor_without_exact_evidence_is_rejected(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive()],
        responses=[_response(anchors=[
            {"type": "operation", "value": "GET /ping", "evidence": []}])])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 2


def test_evidence_naming_a_source_outside_the_manifest_is_rejected(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive()],
        responses=[_response(anchors=[
            {"type": "operation", "value": "GET /ping",
             "evidence": [_evidence(source="ghost.md")]}])])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "ghost.md" in res.output


def test_evidence_whose_digest_does_not_match_the_source_is_rejected(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive()],
        responses=[_response(anchors=[
            {"type": "operation", "value": "GET /ping",
             "evidence": [{**_evidence(), "fragment_digest": "b" * 64}]}])])

    res = _verify(sources, extraction, focus)

    assert res.exit_code == 2


# --- one definition, two entry points -------------------------------------

def test_assemble_reaches_the_same_verdict_as_verify(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive()],
        responses=[_response(anchors=[
            {"type": "operation", "value": "DELETE /ping",
             "evidence": [_evidence()]}])])

    assert _verify(sources, extraction, focus).exit_code == 2

    res = _assemble(tmp_path, sources, extraction, focus)

    assert res.exit_code == 2
    assert "DELETE /ping" in res.output
    assert not (tmp_path / "runs").exists()


def test_assemble_lets_a_clean_focus_package_through_to_generation(tmp_path):
    # 閘門通過 = 建立了 run 目錄。這裡不斷言 exit 0:這份最小 fixture 的
    # validation 結果與 focus 無關,綁上去會讓測試對不相干的改動敏感。
    sources, extraction, focus = _setup(
        tmp_path, directives=[_directive()], responses=[_response()])

    res = _assemble(tmp_path, sources, extraction, focus)

    assert res.exit_code != 2, res.output
    assert list((tmp_path / "runs").iterdir())
