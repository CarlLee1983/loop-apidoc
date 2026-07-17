from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from loop_apidoc.cli import app


runner = CliRunner()


def test_snapshot_openapi_url_command_delegates_to_snapshot_module(tmp_path: Path, monkeypatch):
    calls = []

    def fake_snapshot(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(
            snapshot_path=tmp_path / "sources" / "transfer.json",
            coverage_path=tmp_path / "coverage.json",
            sha256="a" * 64,
        )

    monkeypatch.setattr("loop_apidoc.openapi_snapshot.snapshot_openapi_url", fake_snapshot)
    result = runner.invoke(
        app,
        [
            "snapshot-openapi-url",
            "--url", "https://spec.example.com/transfer.json",
            "--sources", str(tmp_path / "sources"),
            "--coverage", str(tmp_path / "coverage.json"),
            "--filename", "transfer.json",
            "--confirmed-by-user",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert calls == [
        ("https://spec.example.com/transfer.json", {
            "sources": tmp_path / "sources",
            "coverage_output": tmp_path / "coverage.json",
            "filename": "transfer.json",
            "confirmed_by_user": True,
            "max_bytes": 5 * 1024 * 1024,
        })
    ]
    assert "coverage.json" in result.stdout
