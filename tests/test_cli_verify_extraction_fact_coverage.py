"""`verify-extraction` 預告語意完整性閘門對哪些來源不會有作用。

預告的價值在時機:知道這件事的最晚時刻本來是 assemble 跑完看報告,而那時 plan →
generate 的成本已經付掉了。改用保留表格結構的前處理路徑是「重跑前處理」,不是
「重讀來源」,越早知道省得越多。

告知但不阻擋 —— 一旦能擋,等於把被否決的「零事實直接 FAIL」強度裝回去。
"""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app

runner = CliRunner()

_INVENTORY = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "manual.md p.1"}],
    "security_schemes": [], "schemas": [], "errors": [], "operational": [],
    "endpoints": [{"method": "GET", "path": "/ping", "summary": "健康檢查",
                   "source": "manual.md p.2"}],
    "missing": [],
}
_ENDPOINT = {
    "method": "GET", "path": "/ping", "parameters": [], "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [], "missing": [],
}

_FLATTENED = (
    "API 名稱 描述 Ping 健康檢查 傳入參數說明 參數 型態 說明 "
    "WebId string 站台代碼 回傳資訊說明 code int 錯誤代碼"
)


def _setup(tmp_path: Path, *, source_text: str, name: str = "manual.md"):
    extraction = tmp_path / "extraction"
    (extraction / "endpoints").mkdir(parents=True)
    inventory = json.loads(json.dumps(_INVENTORY))
    inventory["environments"][0]["source"] = f"{name} p.1"
    inventory["endpoints"][0]["source"] = f"{name} p.2"
    (extraction / "inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
    (extraction / "endpoints" / "ep0.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / name).write_text(source_text, encoding="utf-8")
    return sources, extraction


def _verify(sources: Path, extraction: Path, *extra: str):
    return runner.invoke(app, [
        "verify-extraction", "--sources", str(sources),
        "--extraction", str(extraction), *extra,
    ])


def test_a_zero_fact_source_is_forecast_by_name(tmp_path):
    sources, extraction = _setup(tmp_path, source_text=_FLATTENED)

    res = _verify(sources, extraction)

    assert "manual.md" in res.output
    assert "0 筆" in res.output or "零事實" in res.output


def test_a_source_with_matching_facts_is_not_forecast(tmp_path):
    sources, extraction = _setup(
        tmp_path, source_text="# Demo API\n\n`GET /ping`\n")

    res = _verify(sources, extraction)

    assert "SOURCE_FACTS_UNSCANNED" not in res.output


def test_facts_that_match_nothing_are_forecast_as_a_different_shape(tmp_path):
    """來源寫了端點、擷取沒有一個對得上 —— 補救是補 extraction,不是換前處理。"""
    sources, extraction = _setup(
        tmp_path, source_text="# Demo API\n\n`GET /elsewhere`\n")

    res = _verify(sources, extraction)

    assert "manual.md:1 筆事實無一對上" in res.output
    assert "manual.md:掃出 0 筆" not in res.output


def test_the_forecast_does_not_change_the_exit_code(tmp_path):
    sources, extraction = _setup(tmp_path, source_text=_FLATTENED)

    assert _verify(sources, extraction).exit_code == 0


def test_the_forecast_stays_out_of_the_json_payload(tmp_path):
    sources, extraction = _setup(tmp_path, source_text=_FLATTENED)

    res = _verify(sources, extraction, "--json")

    assert json.loads(res.stdout) == []


def test_the_forecast_names_an_unclosed_fence(tmp_path):
    """成因已知時,預告就該直接說是哪一行,而不是叫人自己猜。"""
    # 圍籬開在第 3 行且從未關閉,所以其後的 `GET /ping` 宣告根本沒被讀到。
    source = "# Demo API\n\n```json\n{}\n```json\n\n`GET /ping`\n"
    sources, extraction = _setup(tmp_path, source_text=source)

    res = _verify(sources, extraction)

    assert res.exit_code == 0, res.output
    assert "第 3 行" in res.output
