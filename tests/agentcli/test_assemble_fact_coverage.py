"""一次真實的 `assemble` 會不會真的報出 SOURCE_FACTS_UNSCANNED。

單元測試把投影當參數傳進 `validate_outputs`,證明不了接線還在:把 `assemble` 的
`fact_coverage=` 拿掉,那些測試照樣全綠。benchmark 也補不上這個洞——它的來源是
operator 提供且 gitignored 的,clone 後直接 skip。這個檔案自帶來源,所以在乾淨的
CI 上就會開火。
"""
from __future__ import annotations

import json

from tests.focus.support import assemble, setup

_FLATTENED = (
    "API 名稱 描述 Ping 健康檢查 傳入參數說明 參數 型態 說明 "
    "WebId string 站台代碼 回傳資訊說明 code int 錯誤代碼"
)


def _issues(res, code: str) -> list[dict]:
    payload = json.loads(res.stdout)
    return [i for i in payload["report"]["issues"] if i["code"] == code]


def test_assemble_reports_a_source_the_gate_never_judged(tmp_path):
    sources, extraction, _ = setup(tmp_path, extra_sources={"dump.md": _FLATTENED})

    res = assemble(tmp_path, sources, extraction, None, "--json")

    unscanned = _issues(res, "SOURCE_FACTS_UNSCANNED")
    assert [i["location"] for i in unscanned] == ["dump.md"]
    assert unscanned[0]["severity"] == "warning"


def test_the_warning_changes_neither_the_verdict_nor_the_exit_code(tmp_path):
    """加一份閘門判不了的來源,不得改變這次 run 的成敗。"""
    plain_sources, plain_extraction, _ = setup(tmp_path / "plain")
    plain = assemble(tmp_path / "plain", plain_sources, plain_extraction, None, "--json")

    sources, extraction, _ = setup(
        tmp_path / "with-dump", extra_sources={"dump.md": _FLATTENED})
    res = assemble(tmp_path / "with-dump", sources, extraction, None, "--json")

    assert _issues(res, "SOURCE_FACTS_UNSCANNED") != []
    assert res.exit_code == plain.exit_code
    assert json.loads(res.stdout)["ok"] == json.loads(plain.stdout)["ok"]


def test_a_source_whose_facts_match_the_extraction_is_not_reported(tmp_path):
    """manual.md 寫了 `GET /ping`,擷取也有 —— 閘門確實比對過它。"""
    sources, extraction, _ = setup(tmp_path)

    res = assemble(tmp_path, sources, extraction, None, "--json")

    assert _issues(res, "SOURCE_FACTS_UNSCANNED") == []
