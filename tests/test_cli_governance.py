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
