from __future__ import annotations

import json
from datetime import datetime, timezone

from loop_apidoc.run.models import RunDescriptor, RunStatus, Toolchain
from loop_apidoc.run.persist import persist_run_descriptor


def _descriptor() -> RunDescriptor:
    return RunDescriptor(
        run_id="r1",
        status=RunStatus.PASSED,
        generated_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
        toolchain=Toolchain(
            cli_version="0.13.0",
            extraction_contract_version="1",
            skill_version=None,
            model=None,
        ),
    )


def test_persist_run_descriptor_writes_run_json(tmp_path) -> None:
    persist_run_descriptor(tmp_path, _descriptor())
    payload = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == "r1"
    assert payload["status"] == "passed"
    assert payload["toolchain"] == {
        "cli_version": "0.13.0",
        "extraction_contract_version": "1",
        "skill_version": None,
        "model": None,
    }


def test_persist_run_descriptor_keeps_null_fields_explicit(tmp_path) -> None:
    """null 是合法結果(不可捏造),必須留在檔案裡而非被省略。"""
    persist_run_descriptor(tmp_path, _descriptor())
    text = (tmp_path / "run.json").read_text(encoding="utf-8")
    assert '"skill_version": null' in text
    assert '"model": null' in text
