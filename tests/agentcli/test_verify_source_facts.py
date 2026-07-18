"""Issue #14 回歸:完整來源被嚴重擷取不足時,verify-extraction 必須擋下來。

歷史事故的形狀是——來源明明列了參數表與範例,擷取卻交回空清單加一句
「需進一步擷取」,而 run 仍記為 passed。這裡用一份最小化的 ATG 形狀來源
把那個形狀釘住:錯的要 fail,對的要 pass,真實的來源缺口仍只是缺口。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from loop_apidoc.agentcli.verify import verify_extraction_dir

_TS = datetime(2026, 1, 1, tzinfo=UTC)

ATG_SOURCE = """
# ATG Game API

## 遊戲列表

`GET /games`

| 參數名稱 | 型態 | 必填 | 說明 |
| --- | --- | --- | --- |
| X-Token | string | Y | 認證權杖 |
| provider | string | N | 廠商代碼 |
| category | string | N | 分類 |
| rows | int | N | 每頁筆數 |
| page | int | N | 頁碼 |
| sidx | string | N | 排序欄位 |
| locale | string | N | 語系 |
| sord | string | N | 排序方向 |
| type | string | N | 類型 |

```json
{"code": 0, "data": []}
```

## 轉點

`POST /game-providers/{providerId}/balance`

| 參數名稱 | 型態 | 必填 | 說明 |
| --- | --- | --- | --- |
| username | string | Y | 玩家帳號 |
| balance | number | Y | 金額 |
| action | string | Y | 動作 |
| transferId | string | Y | 交易序號 |
"""

_GAMES_FIELDS = [
    "X-Token", "provider", "category", "rows", "page", "sidx", "locale", "sord", "type",
]
_BALANCE_FIELDS = ["username", "balance", "action", "transferId"]


def _write_case(root: Path, endpoint_files: list[dict]) -> tuple[Path, Path]:
    sources = root / "sources"
    sources.mkdir()
    (sources / "atg.md").write_text(ATG_SOURCE, encoding="utf-8")

    extraction = root / "extraction"
    (extraction / "endpoints").mkdir(parents=True)
    inventory = {
        "title": "ATG Game API",
        "version": None,
        "overview": "ATG game integration API.",
        "environments": [],
        "security_schemes": [
            {
                "name": "X-Token",
                "type": "apiKey",
                "location": "header",
                "details": "Authentication token issued to the operator.",
                "source": "atg.md#遊戲列表",
            }
        ],
        "endpoints": [
            {
                "method": endpoint["method"],
                "path": endpoint["path"],
                "summary": endpoint["summary"],
                "source": endpoint["source"],
                "server": None,
            }
            for endpoint in endpoint_files
        ],
        "schemas": [],
        "missing": [],
    }
    (extraction / "inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
    for index, endpoint in enumerate(endpoint_files, start=1):
        (extraction / "endpoints" / f"ep{index}.json").write_text(
            json.dumps(endpoint, ensure_ascii=False), encoding="utf-8")
    return sources, extraction


def _endpoint(method: str, path: str, summary: str, **overrides) -> dict:
    base = {
        "method": method,
        "path": path,
        "summary": summary,
        "source": "atg.md#遊戲列表",
        "parameters": [],
        "request": None,
        "responses": [
            {
                "status": "200",
                "description": "Successful response.",
                "schema": None,
                "source": "atg.md#遊戲列表",
            }
        ],
        "tags": ["ATG"],
        "security": ["X-Token"],
        "examples": [],
        "missing": [],
    }
    return {**base, **overrides}


def _params(names: list[str]) -> list[dict]:
    return [
        {"name": name, "in": "query", "type": "string",
         "required": False, "description": f"Documented field {name}."}
        for name in names
    ]


def _correct_case() -> list[dict]:
    return [
        _endpoint(
            "GET", "/games", "List available games.",
            parameters=_params(_GAMES_FIELDS),
            examples=[{"title": "Success", "body": '{"code": 0, "data": []}'}],
        ),
        _endpoint(
            "POST", "/game-providers/{providerId}/balance", "Transfer balance.",
            parameters=_params(_BALANCE_FIELDS),
        ),
    ]


def _verify(root: Path, endpoint_files: list[dict]) -> list[str]:
    sources, extraction = _write_case(root, endpoint_files)
    return verify_extraction_dir(
        sources_root=sources, extraction_dir=extraction, generated_at=_TS)


def test_the_correctly_extracted_atg_fixture_passes(tmp_path: Path) -> None:
    assert _verify(tmp_path, _correct_case()) == []


def test_the_historically_under_extracted_shape_fails(tmp_path: Path) -> None:
    under_extracted = [
        _endpoint(
            "GET", "/games",
            "detailed parameters and response schema require a further "
            "source-grounded extraction",
        ),
        _endpoint(
            "POST", "/game-providers/{providerId}/balance", "Transfer balance."),
    ]
    violations = _verify(tmp_path, under_extracted)
    assert violations, "an empty extraction over a documented source must not pass"
    joined = "\n".join(violations)
    for field in _GAMES_FIELDS + _BALANCE_FIELDS:
        assert repr(field) in joined
    assert "example" in joined.lower()
    assert "defers the work" in joined


def test_a_partially_extracted_endpoint_names_only_the_omitted_fields(
    tmp_path: Path,
) -> None:
    endpoints = _correct_case()
    endpoints[0]["parameters"] = _params(_GAMES_FIELDS[:4])
    violations = _verify(tmp_path, endpoints)
    joined = "\n".join(violations)
    assert "'page'" in joined and "'sord'" in joined
    assert "'X-Token'" not in joined


def test_a_genuine_source_gap_stays_a_gap_and_never_blocks(tmp_path: Path) -> None:
    """來源真的沒寫的東西,具名記在 missing 就不是遺漏——不得逼出捏造。"""
    endpoints = _correct_case()
    endpoints[1]["parameters"] = _params(_BALANCE_FIELDS[:3])
    endpoints[1]["missing"] = [
        "The source lists `transferId` in the table but never states its format "
        "or maximum length."
    ]
    assert _verify(tmp_path, endpoints) == []
