from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app


runner = CliRunner()


def test_import_rendered_url_writes_immutable_source_provenance_and_coverage(
    tmp_path: Path,
) -> None:
    rendered = tmp_path / "rendered.html"
    raw = b"<main><h1>Quick Start</h1></main>"
    rendered.write_bytes(raw)
    sources = tmp_path / "sources"
    coverage = tmp_path / "url_sources" / "coverage.json"

    result = runner.invoke(
        app,
        [
            "import-rendered-url",
            "--input",
            str(rendered),
            "--url",
            "https://docs.example.com/quickstart/#top",
            "--captured-at",
            "2026-07-29T08:30:00+08:00",
            "--capture-method",
            "browser_save",
            "--sources",
            str(sources),
            "--coverage",
            str(coverage),
            "--confirmed-by-user",
        ],
    )

    assert result.exit_code == 0, result.stdout
    imported = sources / "rendered.html"
    assert imported.read_bytes() == raw
    digest = hashlib.sha256(raw).hexdigest()
    provenance = json.loads(
        imported.with_suffix(".html.source.json").read_text(encoding="utf-8")
    )
    assert provenance == {
        "schema_version": 1,
        "original_url": "https://docs.example.com/quickstart/#top",
        "canonical_url": "https://docs.example.com/quickstart",
        "captured_at": "2026-07-29T08:30:00+08:00",
        "capture_method": "browser_save",
        "imported_sha256": digest,
        "source_file": "rendered.html",
    }
    ledger = json.loads(coverage.read_text(encoding="utf-8"))
    assert ledger["entry_url"] == "https://docs.example.com/quickstart"
    assert ledger["confirmed_by_user"] is True
    assert ledger["results"] == [
        {
            "url": "https://docs.example.com/quickstart",
            "status": "fetched_rendered",
            "file": "rendered.html",
            "method": "browser",
            "provenance_file": "rendered.html.source.json",
        }
    ]


def test_manifest_uses_verified_rendered_coverage_without_origin_fetch(
    tmp_path: Path, monkeypatch
) -> None:
    rendered = tmp_path / "rendered.html"
    rendered.write_text("<main>Protected contract</main>", encoding="utf-8")
    sources = tmp_path / "sources"
    coverage = tmp_path / "url_sources" / "coverage.json"
    imported = runner.invoke(
        app,
        [
            "import-rendered-url",
            "--input",
            str(rendered),
            "--url",
            "https://protected.example.com/contract/",
            "--captured-at",
            "2026-07-29T00:30:00Z",
            "--capture-method",
            "playwright",
            "--sources",
            str(sources),
            "--coverage",
            str(coverage),
        ],
    )
    assert imported.exit_code == 0, imported.stdout

    def unexpected_probe(*args, **kwargs):
        raise AssertionError("protected origin must not be fetched")

    monkeypatch.setattr("loop_apidoc.manifest.builder.probe_url", unexpected_probe)
    manifest_path = tmp_path / "manifest.json"
    result = runner.invoke(
        app,
        [
            "manifest",
            "--sources",
            str(sources),
            "--url",
            "https://protected.example.com/contract",
            "--url-coverage",
            str(coverage),
            "--output",
            str(manifest_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["url_sources"] == [
        {
            "url": "https://protected.example.com/contract",
            "fetched_at": "2026-07-29T00:30:00Z",
            "http_status": None,
            "content_sha256": hashlib.sha256(
                b"<main>Protected contract</main>"
            ).hexdigest(),
            "note": "fetched_rendered",
            "snapshot_file": "rendered.html",
        }
    ]


def test_manifest_rejects_tampered_rendered_provenance_without_origin_fetch(
    tmp_path: Path, monkeypatch
) -> None:
    rendered = tmp_path / "rendered.md"
    rendered.write_text("# Protected contract\n", encoding="utf-8")
    sources = tmp_path / "sources"
    coverage = tmp_path / "url_sources" / "coverage.json"
    imported = runner.invoke(
        app,
        [
            "import-rendered-url",
            "--input",
            str(rendered),
            "--url",
            "https://protected.example.com/contract",
            "--captured-at",
            "2026-07-29T00:30:00Z",
            "--capture-method",
            "browser_save",
            "--sources",
            str(sources),
            "--coverage",
            str(coverage),
        ],
    )
    assert imported.exit_code == 0, imported.stdout
    provenance_path = sources / "rendered.md.source.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["imported_sha256"] = "0" * 64
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")

    def unexpected_probe(*args, **kwargs):
        raise AssertionError("invalid rendered evidence must fail before fetching")

    monkeypatch.setattr("loop_apidoc.manifest.builder.probe_url", unexpected_probe)
    result = runner.invoke(
        app,
        [
            "manifest",
            "--sources",
            str(sources),
            "--url",
            "https://protected.example.com/contract",
            "--url-coverage",
            str(coverage),
        ],
    )

    assert result.exit_code == 2
    assert "SHA-256 does not match provenance" in result.output


def test_manifest_rejects_rendered_coverage_url_mismatch_without_origin_fetch(
    tmp_path: Path, monkeypatch
) -> None:
    rendered = tmp_path / "rendered.html"
    rendered.write_text("<main>Contract</main>", encoding="utf-8")
    sources = tmp_path / "sources"
    coverage = tmp_path / "url_sources" / "coverage.json"
    imported = runner.invoke(
        app,
        [
            "import-rendered-url",
            "--input",
            str(rendered),
            "--url",
            "https://docs.example.com/contract",
            "--captured-at",
            "2026-07-29T00:30:00Z",
            "--capture-method",
            "browser_save",
            "--sources",
            str(sources),
            "--coverage",
            str(coverage),
        ],
    )
    assert imported.exit_code == 0, imported.stdout
    ledger = json.loads(coverage.read_text(encoding="utf-8"))
    ledger["results"][0]["url"] = "https://docs.example.com/different"
    coverage.write_text(json.dumps(ledger), encoding="utf-8")

    def unexpected_probe(*args, **kwargs):
        raise AssertionError("mismatched rendered coverage must fail before fetching")

    monkeypatch.setattr("loop_apidoc.manifest.builder.probe_url", unexpected_probe)
    result = runner.invoke(
        app,
        [
            "manifest",
            "--sources",
            str(sources),
            "--url",
            "https://docs.example.com/contract",
            "--url-coverage",
            str(coverage),
        ],
    )

    assert result.exit_code == 2
    assert "not present in requested URLs" in result.output


def test_import_rendered_url_rejects_malformed_capture_time_and_overwrite(
    tmp_path: Path,
) -> None:
    rendered = tmp_path / "rendered.html"
    rendered.write_text("<main>Contract</main>", encoding="utf-8")
    sources = tmp_path / "sources"
    coverage = tmp_path / "url_sources" / "coverage.json"
    base_args = [
        "import-rendered-url",
        "--input",
        str(rendered),
        "--url",
        "https://docs.example.com/contract",
        "--capture-method",
        "browser_save",
        "--sources",
        str(sources),
        "--coverage",
        str(coverage),
    ]

    malformed = runner.invoke(
        app, [*base_args, "--captured-at", "2026-07-29T08:30:00"]
    )
    assert malformed.exit_code == 2
    assert "timezone offset" in malformed.output
    assert not (sources / "rendered.html").exists()

    first = runner.invoke(
        app, [*base_args, "--captured-at", "2026-07-29T08:30:00+08:00"]
    )
    assert first.exit_code == 0, first.stdout
    before = (sources / "rendered.html").read_bytes()
    second = runner.invoke(
        app, [*base_args, "--captured-at", "2026-07-29T09:00:00+08:00"]
    )
    assert second.exit_code == 2
    assert "output already exists" in second.output
    assert (sources / "rendered.html").read_bytes() == before
