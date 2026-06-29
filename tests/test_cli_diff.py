from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.validate.models import ValidationReport

runner = CliRunner()
_NOW = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


def _openapi(path: str) -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "paths": {
            path: {
                "get": {
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }


def _write_run(run_dir: Path, path: str) -> Path:
    run_dir.mkdir(parents=True)
    (run_dir / "openapi.yaml").write_text(
        yaml.safe_dump(_openapi(path), sort_keys=False),
        encoding="utf-8",
    )
    (run_dir / "provenance.json").write_text(
        ProvenanceDocument(notebook_url="", entries=[]).model_dump_json(indent=2),
        encoding="utf-8",
    )
    (run_dir / "validation").mkdir()
    (run_dir / "validation" / "report.json").write_text(
        ValidationReport().model_dump_json(indent=2),
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        Manifest(sources_root="./sources", generated_at=_NOW).model_dump_json(indent=2),
        encoding="utf-8",
    )
    return run_dir


def test_diff_writes_default_reports_under_head_run(tmp_path):
    base = _write_run(tmp_path / "base", "/payments")
    head = _write_run(tmp_path / "head", "/payments")
    head_doc = yaml.safe_load((head / "openapi.yaml").read_text(encoding="utf-8"))
    head_doc["paths"]["/refunds"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    (head / "openapi.yaml").write_text(
        yaml.safe_dump(head_doc, sort_keys=False),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["diff", "--base", str(base), "--head", str(head)])

    assert result.exit_code == 0
    report_json = head / "diff" / "report.json"
    report_md = head / "diff" / "report.md"
    assert report_json.is_file()
    assert report_md.is_file()
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["summary"]["additive"] == 1
    assert "diff/report.json" in result.stdout


def test_diff_writes_output_override(tmp_path):
    base = _write_run(tmp_path / "base", "/payments")
    head = _write_run(tmp_path / "head", "/refunds")
    out = tmp_path / "custom-diff"

    result = runner.invoke(
        app,
        ["diff", "--base", str(base), "--head", str(head), "--output", str(out)],
    )

    assert result.exit_code == 0
    assert (out / "report.json").is_file()
    assert (out / "report.md").is_file()


def test_diff_invalid_input_exits_2_without_output_dir(tmp_path):
    base = _write_run(tmp_path / "base", "/payments")
    head = _write_run(tmp_path / "head", "/refunds")
    (head / "manifest.json").unlink()

    result = runner.invoke(app, ["diff", "--base", str(base), "--head", str(head)])

    assert result.exit_code == 2
    assert not (head / "diff").exists()
    assert "diff input error" in result.stderr


def test_diff_output_path_as_file_exits_2(tmp_path):
    base = _write_run(tmp_path / "base", "/payments")
    head = _write_run(tmp_path / "head", "/refunds")
    out = tmp_path / "report-file"
    out.write_text("not a directory", encoding="utf-8")

    result = runner.invoke(
        app,
        ["diff", "--base", str(base), "--head", str(head), "--output", str(out)],
    )

    assert result.exit_code == 2
    assert "output path is a file" in result.stderr
