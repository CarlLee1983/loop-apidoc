"""落空的 directive 的語意結局:走 ValidationReport,不走輸入閘。

分界的理由在結局本身:結構壞掉時 agent 只需要改檔,給它一行訊息就夠;斷言落空
時人要判斷「是來源真的沒有,還是查得不夠」,而那需要 run 目錄、產物與應答一起
留在手上。所以這裡每個測試都同時斷言「產物有出來」。
"""
from __future__ import annotations

import json

from tests.focus.support import (
    assemble,
    directive,
    error_codes,
    issues_with_code,
    not_found,
    response,
    setup,
    verify,
)


def _json_payload(res) -> dict:
    return json.loads(res.stdout)


def test_a_falsified_expectation_is_an_error_issue(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[not_found()])

    res = assemble(tmp_path, sources, extraction, focus, "--json")
    payload = _json_payload(res)

    assert "FOCUS_UNMET" in error_codes(payload)
    assert payload["ok"] is False
    assert res.exit_code == 1


def test_a_falsified_expectation_still_produces_the_run_artifacts(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[not_found()])

    res = assemble(tmp_path, sources, extraction, focus, "--json")
    payload = _json_payload(res)
    run_dir = tmp_path / "runs" / payload["run_id"]

    assert (run_dir / "openapi.yaml").exists()
    assert (run_dir / "review.html").exists()


def test_the_issue_names_the_directive_and_the_sources_searched(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[not_found()])

    payload = _json_payload(assemble(tmp_path, sources, extraction, focus, "--json"))
    issue = issues_with_code(payload, "FOCUS_UNMET")[0]

    assert "ping" in issue["location"]
    assert "manual.md" in issue["evidence"]


def test_a_coverage_directive_coming_back_empty_is_only_a_warning(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive(kind="coverage")],
        responses=[not_found()])

    payload = _json_payload(assemble(tmp_path, sources, extraction, focus, "--json"))
    unmet = issues_with_code(payload, "FOCUS_UNMET")

    assert [i["severity"] for i in unmet] == ["warning"]
    assert "FOCUS_UNMET" not in error_codes(payload)


def test_a_coverage_not_found_adds_no_error_the_run_would_not_have_had(tmp_path):
    # 這份最小 fixture 自己就帶著與 focus 無關的 error,所以「不阻斷」要用
    # 「error 集合與沒有 focus 時相同」來驗,而不是綁 exit 0。
    sources, extraction, focus = setup(
        tmp_path, directives=[directive(kind="coverage")],
        responses=[not_found()])
    baseline = _json_payload(assemble(tmp_path, sources, extraction, None, "--json"))

    focused = _json_payload(assemble(tmp_path, sources, extraction, focus, "--json"))

    assert sorted(error_codes(focused)) == sorted(error_codes(baseline))


def test_a_satisfied_directive_produces_no_issue(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[response()])

    payload = _json_payload(assemble(tmp_path, sources, extraction, focus, "--json"))

    assert issues_with_code(payload, "FOCUS_UNMET") == []


def test_severity_cannot_be_overridden_per_directive(tmp_path):
    # kind 是 severity 的唯一來源。想要不阻斷就寫 coverage,不是加旗標。
    sources, extraction, focus = setup(
        tmp_path, directives=[directive(on_not_found="warn")],
        responses=[not_found()])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "on_not_found" in res.output


# --- ADR 0004:focus 不得洩漏到跨 run 可比的產物 ---------------------------

def test_focus_changes_neither_the_score_nor_provenance(tmp_path):
    # 同一份來源、不同 focus 的兩次 run,分數與 provenance 必須逐位元組相同。
    # 否則「來源說了什麼」就被「誰問了什麼」污染,跨 run 比對與 Foundry 審批
    # 都失去意義,而提出者還能靠寫寬鬆的 directive 把分數拉高。
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[not_found()])

    plain = _json_payload(
        assemble(tmp_path, sources, extraction, None, "--json", "--score"))
    focused = _json_payload(
        assemble(tmp_path, sources, extraction, focus, "--json", "--score"))

    assert focused["score"]["score"] == plain["score"]["score"]
    assert all("FOCUS" not in f["code"] for f in focused["score"]["findings"])

    def provenance(payload: dict) -> bytes:
        return (tmp_path / "runs" / payload["run_id"] / "provenance.json").read_bytes()

    assert provenance(focused) == provenance(plain)


# --- verify-extraction 的預告 ----------------------------------------------

def test_verify_previews_the_count_of_falsified_expectations(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[not_found()])

    res = verify(sources, extraction, focus)

    assert "1" in res.output
    assert "expectation" in res.output.lower()


def test_verify_does_not_fail_on_a_falsified_expectation(tmp_path):
    # 預告不得影響 exit code —— 否則好不容易切開的兩層又混回去了,
    # 落空的斷言會退回「沒有產物可看」的結局。
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[not_found()])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 0, res.output


def test_verify_json_output_stays_a_pure_violation_array(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[not_found()])

    res = verify(sources, extraction, focus, "--json")

    assert json.loads(res.stdout) == []
