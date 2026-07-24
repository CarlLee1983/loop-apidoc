from __future__ import annotations

from pathlib import Path

import pytest

from loop_apidoc.freshness.models import (
    BatchItemResult,
    BatchItemStatus,
    BatchReport,
    FreshnessVerdict,
    SourceKind,
    SourceObservation,
    SourceSignal,
    SourceStatus,
)
from loop_apidoc.freshness.signals import hash_bytes
from loop_apidoc.governance.snapshot import GovernanceSnapshotError, write_snapshot


def _changed_scan(raw: bytes) -> BatchReport:
    return BatchReport(
        verdict=FreshnessVerdict.CHANGED,
        total=1,
        changed_count=1,
        attention_count=0,
        unchanged_count=0,
        items=[BatchItemResult(
            label="public-api",
            status=BatchItemStatus.CHANGED,
            observations=[SourceObservation(
                id="https://api.example.test/openapi.json",
                kind=SourceKind.OPENAPI_URL,
                status=SourceStatus.CHANGED,
                signal=SourceSignal(sha256=hash_bytes(raw), version="2"),
                raw=raw,
            )],
        )],
    )


def test_write_snapshot_retains_changed_url_bytes_and_refuses_overwrite(tmp_path: Path):
    raw = b'{"openapi":"3.1.0","info":{"version":"2"}}'
    snapshot_dir = tmp_path / "snapshot"

    snapshot = write_snapshot(_changed_scan(raw), snapshot_dir)

    assert snapshot is not None
    source = snapshot.items[0].sources[0]
    assert (snapshot_dir / source.path).read_bytes() == raw
    with pytest.raises(GovernanceSnapshotError, match="already exists"):
        write_snapshot(_changed_scan(raw), snapshot_dir)


def test_write_snapshot_does_not_create_an_empty_pack_for_unchanged_scan(tmp_path: Path):
    scan = BatchReport(
        verdict=FreshnessVerdict.UNCHANGED,
        total=1,
        changed_count=0,
        attention_count=0,
        unchanged_count=1,
        items=[BatchItemResult(label="public-api", status=BatchItemStatus.UNCHANGED)],
    )

    assert write_snapshot(scan, tmp_path / "snapshot") is None
    assert not (tmp_path / "snapshot").exists()
