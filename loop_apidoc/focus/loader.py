"""這個套件唯一的讀取出口:把提出者的 focus 檔與 agent 的應答讀成型別。

硬 schema 錯誤(JSON 壞掉、未知結局、缺必填欄位)在這裡就 fail loudly —— 它們
會讓後續每一項檢查失去意義。契約違規(id 對不上、錨點指不到)留給 `gate`。
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from loop_apidoc.focus.models import FocusFile, FocusPackage, FocusResponseFile

RESPONSE_FILENAME = "focus-response.json"


class FocusInputError(Exception):
    """focus 輸入無法解析;呼叫端轉成 exit 2,不建立 run 目錄。"""


def _read_json(path: Path, label: str) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FocusInputError(f"{label} 不存在:{path}") from exc
    except OSError as exc:
        raise FocusInputError(f"{label} 無法讀取:{path}({exc})") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FocusInputError(f"{label} 不是合法 JSON:{exc}") from exc
    if not isinstance(payload, dict):
        raise FocusInputError(f"{label} 最外層必須是物件")
    return payload


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    location = ".".join(str(part) for part in err["loc"]) or "(root)"
    return f"{location}: {err['msg']}"


def load_focus_package(focus_file: Path, extraction_dir: Path) -> FocusPackage:
    """讀 focus.json 與擷取目錄裡的 focus-response.json。"""
    directives_payload = _read_json(focus_file, "focus.json")
    try:
        parsed_focus = FocusFile.model_validate(directives_payload)
    except ValidationError as exc:
        raise FocusInputError(
            f"focus.json 不符契約 —— {_first_error(exc)}") from exc

    response_path = extraction_dir / RESPONSE_FILENAME
    responses_payload = _read_json(response_path, RESPONSE_FILENAME)
    try:
        parsed_responses = FocusResponseFile.model_validate(responses_payload)
    except ValidationError as exc:
        raise FocusInputError(
            f"{RESPONSE_FILENAME} 不符契約 —— {_first_error(exc)}") from exc

    return FocusPackage(
        directives=parsed_focus.directives,
        responses=parsed_responses.responses,
    )
