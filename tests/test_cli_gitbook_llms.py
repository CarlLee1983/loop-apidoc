from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.gitbook_llms import GitBookCacheResult, GitBookLlmsError


runner = CliRunner()


def test_cache_gitbook_llms_exposes_explicit_source_and_coverage_paths(tmp_path: Path, monkeypatch):
    sources = tmp_path / "sources"
    coverage = tmp_path / "coverage.json"
    calls: list[tuple[str, Path, Path]] = []

    def fake_cache(url: str, *, sources: Path, coverage_output: Path, **_kwargs):
        calls.append((url, sources, coverage_output))
        return GitBookCacheResult(
            index_url="https://docs.example.com/sample-docs/llms.txt",
            sources=sources,
            coverage_path=coverage_output,
            fetched=2,
            failed=1,
        )

    monkeypatch.setattr("loop_apidoc.gitbook_llms.cache_gitbook_llms", fake_cache)

    result = runner.invoke(
        app,
        [
            "cache-gitbook-llms",
            "--url", "https://docs.example.com/sample-docs",
            "--sources", str(sources),
            "--coverage", str(coverage),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert calls == [("https://docs.example.com/sample-docs", sources, coverage)]
    assert json.loads(result.stdout) == {
        "index_url": "https://docs.example.com/sample-docs/llms.txt",
        "sources": str(sources),
        "coverage": str(coverage),
        "fetched": 2,
        "fetch_failed": 1,
    }


def test_cache_gitbook_llms_uses_exit_two_for_invalid_index(tmp_path: Path, monkeypatch):
    def fail(*_args, **_kwargs):
        raise GitBookLlmsError("no eligible Markdown URLs")

    monkeypatch.setattr("loop_apidoc.gitbook_llms.cache_gitbook_llms", fail)

    result = runner.invoke(
        app,
        [
            "cache-gitbook-llms",
            "--url", "https://docs.example.com/sample-docs",
            "--sources", str(tmp_path / "sources"),
            "--coverage", str(tmp_path / "coverage.json"),
        ],
    )

    assert result.exit_code == 2
    assert "cache-gitbook-llms error: no eligible Markdown URLs" in result.output


def test_cache_gitbook_llms_does_not_echo_a_credential_on_stdout(tmp_path: Path, monkeypatch):
    """Issue #156. The command's own JSON output is an artifact too — it is
    routinely redirected into a file or a run log."""
    signed = "https://docs.example.com/sample-docs/llms.txt?token=s3cret&v=1"

    def fake_cache(url: str, *, sources: Path, coverage_output: Path, **_kwargs):
        return GitBookCacheResult(
            index_url=signed,
            sources=sources,
            coverage_path=coverage_output,
            fetched=1,
            failed=0,
        )

    monkeypatch.setattr("loop_apidoc.gitbook_llms.cache_gitbook_llms", fake_cache)

    result = runner.invoke(
        app,
        [
            "cache-gitbook-llms",
            "--url", "https://docs.example.com/sample-docs",
            "--sources", str(tmp_path / "sources"),
            "--coverage", str(tmp_path / "coverage.json"),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "s3cret" not in result.stdout
    assert json.loads(result.stdout)["index_url"] == (
        "https://docs.example.com/sample-docs/llms.txt?token=[REDACTED]&v=1"
    )
