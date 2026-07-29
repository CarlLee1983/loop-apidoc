from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app


runner = CliRunner()


def test_assess_sources_reject_writes_actionable_report(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"sources_root": str(sources), "generated_at": "2026-07-13T00:00:00Z"}),
        encoding="utf-8",
    )
    observations = tmp_path / "observations.json"
    observations.write_text(
        json.dumps([{
            "source": "supplier.pdf", "locator": "p. 12", "category": "table_unreadable",
            "evidence": "The required parameter table is unreadable.", "severity": "blocker",
            "required_supplement": "Provide the original spreadsheet.",
            "acceptance_criteria": "The table identifies fields and required status.",
        }]),
        encoding="utf-8",
    )
    output = tmp_path / "quality"

    result = runner.invoke(app, [
        "assess-sources", "--sources", str(sources), "--manifest", str(manifest),
        "--observations", str(observations), "--source-set", "v2", "--output", str(output),
    ])

    assert result.exit_code == 1, result.stdout
    assert (output / "source-quality-report.json").is_file()
    assert "請補" in (output / "source-quality-report.zh-TW.md").read_text(encoding="utf-8")


def test_assess_sources_writes_source_diff_for_baseline(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "sources_root": str(sources), "generated_at": "2026-07-13T00:00:00Z",
        "local_sources": [{
            "relative_path": "manual.md", "mime_type": "text/markdown",
            "source_format": "markdown", "size_bytes": 12, "sha256": "new",
            "scanned_at": "2026-07-13T00:00:00Z", "supported": True, "status": "pending",
        }],
    }), encoding="utf-8")
    base = tmp_path / "base.json"
    base.write_text(manifest.read_text(encoding="utf-8").replace('"new"', '"old"'), encoding="utf-8")
    observations = tmp_path / "observations.json"
    observations.write_text("[]", encoding="utf-8")
    output = tmp_path / "quality"

    result = runner.invoke(app, [
        "assess-sources", "--sources", str(sources), "--manifest", str(manifest),
        "--observations", str(observations), "--source-set", "v2", "--output", str(output),
        "--base-manifest", str(base),
    ])

    assert result.exit_code == 0, result.stdout
    assert json.loads((output / "source-diff.json").read_text(encoding="utf-8"))["entries"][0]["kind"] == "changed"


def test_assess_sources_reject_lists_explicit_linked_contract_candidates(
    tmp_path: Path,
) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    quickstart = sources / "quickstart.md"
    quickstart.write_text(
        "# Quick Start\n\nSee [Action](https://docs.example.com/action), "
        "[Encryption](https://docs.example.com/encryption), and "
        "[Callback](https://docs.example.com/callback).\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest_result = runner.invoke(
        app,
        ["manifest", "--sources", str(sources), "--output", str(manifest)],
    )
    assert manifest_result.exit_code == 0, manifest_result.stdout
    observations = tmp_path / "observations.json"
    observations.write_text(
        json.dumps(
            [
                {
                    "source": "quickstart.md",
                    "locator": "Quick Start links",
                    "category": "linked_contracts_missing",
                    "evidence": "The page links to contract details instead of stating them.",
                    "severity": "blocker",
                    "required_supplement": "Capture the explicitly linked contract pages.",
                    "acceptance_criteria": "The source set states the referenced contracts.",
                    "required_source_refs": [
                        "https://docs.example.com/action",
                        "https://docs.example.com/encryption",
                        "https://docs.example.com/callback",
                        "https://docs.example.com/action",
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "quality"

    result = runner.invoke(
        app,
        [
            "assess-sources",
            "--sources",
            str(sources),
            "--manifest",
            str(manifest),
            "--observations",
            str(observations),
            "--source-set",
            "quickstart-only",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 1
    report = json.loads(
        (output / "source-quality-report.json").read_text(encoding="utf-8")
    )
    assert report["verdict"] == "reject"
    assert report["required_source_refs"] == [
        "https://docs.example.com/action",
        "https://docs.example.com/encryption",
        "https://docs.example.com/callback",
    ]
