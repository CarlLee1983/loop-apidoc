from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.freshness.models import SourceFingerprint
from loop_apidoc.freshness.signals import hash_bytes


runner = CliRunner()


def _changed_watchlist(tmp_path: Path) -> Path:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "spec.pdf").write_bytes(b"current source")
    fingerprint = SourceFingerprint(
        sources=[{
            "id": "spec.pdf",
            "kind": "local_file",
            "signal": {"sha256": hash_bytes(b"previous source")},
        }],
    )
    (tmp_path / "baseline.json").write_text(fingerprint.model_dump_json(), encoding="utf-8")
    watchlist = tmp_path / "freshness-watchlist.json"
    watchlist.write_text(
        json.dumps({
            "schema_version": 1,
            "items": [{
                "label": "payment-api",
                "fingerprint": "baseline.json",
                "sources": "sources",
                "run_dir": "runs/payment-api",
            }],
        }),
        encoding="utf-8",
    )
    return watchlist


def test_governance_scan_writes_a_review_trigger_for_a_changed_source(tmp_path: Path):
    watchlist = _changed_watchlist(tmp_path)
    report_dir = tmp_path / "governance"

    result = runner.invoke(
        app,
        ["governance-scan", "--watchlist", str(watchlist), "--report-dir", str(report_dir), "--json"],
    )

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["status"] == "review_required"
    assert report["triggers"] == [{
        "label": "payment-api",
        "kind": "source_changed",
        "reason": "spec.pdf: content hash changed",
        "run_dir": "runs/payment-api",
    }]
    assert (report_dir / "governance-trigger.json").exists()
    assert (report_dir / "governance-trigger.md").exists()


def test_governance_scan_retains_content_addressed_snapshot_for_changed_source(tmp_path: Path):
    watchlist = _changed_watchlist(tmp_path)
    snapshot_dir = tmp_path / "snapshots"

    result = runner.invoke(
        app,
        ["governance-scan", "--watchlist", str(watchlist), "--snapshot-dir", str(snapshot_dir), "--json"],
    )

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    snapshot = report["snapshot"]
    assert snapshot["source_count"] == 1
    assert snapshot["items"] == [{
        "label": "payment-api",
        "sources": [{
            "id": "spec.pdf",
            "kind": "local_file",
            "sha256": hash_bytes(b"current source"),
            "path": f"sources/{hash_bytes(b'current source')}.source",
        }],
    }]
    assert (snapshot_dir / "governance-snapshot.json").is_file()
    assert (snapshot_dir / "sources" / f"{hash_bytes(b'current source')}.source").read_bytes() == b"current source"


def test_governance_review_plan_writes_a_bounded_handoff_from_trigger_and_snapshot(tmp_path: Path):
    watchlist = _changed_watchlist(tmp_path)
    trigger_dir = tmp_path / "trigger"
    snapshot_dir = tmp_path / "snapshot"
    scan = runner.invoke(
        app,
        [
            "governance-scan", "--watchlist", str(watchlist),
            "--report-dir", str(trigger_dir), "--snapshot-dir", str(snapshot_dir),
        ],
    )
    assert scan.exit_code == 1
    output = tmp_path / "review-plan"

    result = runner.invoke(
        app,
        [
            "governance-review-plan",
            "--trigger", str(trigger_dir / "governance-trigger.json"),
            "--snapshot", str(snapshot_dir),
            "--output", str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["items"] == [{
        "label": "payment-api",
        "kind": "source_changed",
        "reason": "spec.pdf: content hash changed",
        "run_dir": "runs/payment-api",
        "sources": [{
            "id": "spec.pdf",
            "sha256": hash_bytes(b"current source"),
            "path": f"sources/{hash_bytes(b'current source')}.source",
        }],
        "required_steps": [
            "Review the retained source bytes against the changed-source trigger.",
            "Re-extract into a separate work directory and run verify-extraction.",
            "Assemble, inspect the impact diff, then request explicit human approval.",
        ],
    }]
    assert (output / "governance-review-plan.json").is_file()
    assert (output / "governance-review-plan.md").is_file()
