"""focus CLI 測試共用的最小 run fixture。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.domain.evidence import fragment_digest
from tests.source_quality_support import write_passing_source_quality

runner = CliRunner()

NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)
SOURCE = "# Demo API\nGET /ping\nPing the service\nPOST /notify\nSettle callback\n"

INVENTORY = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "manual.md lines 1-1"}],
    "security_schemes": [], "schemas": [], "errors": [], "operational": [],
    "endpoints": [
        {"method": "GET", "path": "/ping", "summary": "Ping the service",
         "source": "manual.md lines 2-3"},
        {"method": "POST", "path": None, "summary": "Settle callback",
         "source": "manual.md lines 4-5"},
    ],
    "missing": [],
}
ENDPOINTS = [
    {"method": "GET", "path": "/ping", "summary": "Ping the service",
     "source": "manual.md lines 2-3", "parameters": [], "request": None,
     "responses": [{"status": "200", "description": "OK", "schema": None}],
     "examples": [], "missing": []},
    {"method": "POST", "path": None, "summary": "Settle callback",
     "source": "manual.md lines 4-5", "parameters": [], "request": None,
     "responses": [{"status": "200", "description": "OK", "schema": None}],
     "examples": [], "missing": []},
]


def evidence(*, source: str = "manual.md", line: int = 3,
             text: str = "Ping the service") -> dict:
    return {
        "version": 1,
        "source": source,
        "locator": {"kind": "line_range", "start_line": line, "end_line": line},
        "fragment_digest": fragment_digest(text),
        "claim_path": "/summary",
    }


def directive(**overrides) -> dict:
    return {"id": "ping", "kind": "expectation", "intent": "find_operation",
            "text": "一定要找到健康檢查端點", **overrides}


def response(**overrides) -> dict:
    return {"id": "ping", "outcome": "satisfied", "reported_by": "ep0",
            "anchors": [{"type": "operation", "value": "GET /ping",
                         "evidence": [evidence()]}], **overrides}


def not_found(**overrides) -> dict:
    return {"id": "ping", "outcome": "not_found", "reported_by": "inventory",
            "searched_sources": ["manual.md"], **overrides}


def setup(tmp_path: Path, *, directives=None, responses=None,
          focus_body=None, response_body=None,
          extra_sources: dict[str, str | bytes] | None = None,
          ) -> tuple[Path, Path, Path]:
    extraction = tmp_path / "extraction"
    (extraction / "endpoints").mkdir(parents=True)
    (extraction / "inventory.json").write_text(
        json.dumps(INVENTORY, ensure_ascii=False), encoding="utf-8")
    for index, endpoint in enumerate(ENDPOINTS):
        (extraction / "endpoints" / f"ep{index}.json").write_text(
            json.dumps(endpoint, ensure_ascii=False), encoding="utf-8")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "manual.md").write_text(SOURCE, encoding="utf-8")
    for name, body in (extra_sources or {}).items():
        target = sources / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            target.write_bytes(body)
        else:
            target.write_text(body, encoding="utf-8")

    focus = tmp_path / "focus.json"
    if focus_body is not None:
        focus.write_text(focus_body, encoding="utf-8")
    elif directives is not None:
        focus.write_text(json.dumps(
            {"version": 1, "directives": directives}, ensure_ascii=False),
            encoding="utf-8")

    if response_body is not None:
        (extraction / "focus-response.json").write_text(
            response_body, encoding="utf-8")
    elif responses is not None:
        (extraction / "focus-response.json").write_text(json.dumps(
            {"version": 1, "responses": responses}, ensure_ascii=False),
            encoding="utf-8")
    return sources, extraction, focus


def verify(sources: Path, extraction: Path, focus: Path | None = None, *extra):
    args = ["verify-extraction", "--sources", str(sources),
            "--extraction", str(extraction)]
    if focus is not None:
        args += ["--focus", str(focus)]
    return runner.invoke(app, [*args, *extra])


def assemble(tmp_path: Path, sources: Path, extraction: Path,
             focus: Path | None = None, *extra):
    quality = write_passing_source_quality(
        sources_root=sources, output=tmp_path / "sq", generated_at=NOW)
    args = ["assemble", "--sources", str(sources), "--extraction", str(extraction),
            "--output", str(tmp_path / "runs"), "--source-quality", str(quality)]
    if focus is not None:
        args += ["--focus", str(focus)]
    return runner.invoke(app, [*args, *extra])


def error_codes(payload: dict) -> list[str]:
    return [i["code"] for i in payload["report"]["issues"]
            if i["severity"] == "error"]


def issues_with_code(payload: dict, code: str) -> list[dict]:
    return [i for i in payload["report"]["issues"] if i["code"] == code]
