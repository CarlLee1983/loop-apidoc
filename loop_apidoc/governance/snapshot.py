"""Immutable, content-addressed evidence packs for changed governance sources."""

from __future__ import annotations

import tempfile
from pathlib import Path

from loop_apidoc.freshness.models import BatchItemStatus, BatchReport, SourceStatus
from loop_apidoc.freshness.signals import hash_bytes
from loop_apidoc.governance.models import GovernanceSnapshot, GovernanceSnapshotItem, GovernanceSnapshotSource


class GovernanceSnapshotError(Exception):
    """A changed source could not become a reproducible governance snapshot."""


def write_snapshot(scan: BatchReport, snapshot_dir: Path) -> GovernanceSnapshot | None:
    """Write changed source bytes once, refusing to overwrite an evidence pack."""
    if snapshot_dir.exists():
        raise GovernanceSnapshotError(f"snapshot directory already exists: {snapshot_dir}")

    items: list[tuple[str, list[tuple[GovernanceSnapshotSource, bytes]]]] = []
    for item in scan.items:
        if item.status is not BatchItemStatus.CHANGED:
            continue
        sources: list[tuple[GovernanceSnapshotSource, bytes]] = []
        for observed in item.observations:
            if observed.status is not SourceStatus.CHANGED:
                continue
            if observed.raw is None or observed.signal is None or observed.signal.sha256 is None:
                raise GovernanceSnapshotError(f"changed source was not retained during scan: {item.label}/{observed.id}")
            digest = hash_bytes(observed.raw)
            if digest != observed.signal.sha256:
                raise GovernanceSnapshotError(f"changed source digest mismatch: {item.label}/{observed.id}")
            relative_path = f"sources/{digest}.source"
            sources.append((GovernanceSnapshotSource(
                id=observed.id, kind=observed.kind, sha256=digest, path=relative_path,
            ), observed.raw))
        if not sources:
            raise GovernanceSnapshotError(f"changed item had no retained source bytes: {item.label}")
        items.append((item.label, sources))

    if not items:
        return None

    snapshot = GovernanceSnapshot(
        source_count=sum(len(sources) for _, sources in items),
        items=[GovernanceSnapshotItem(label=label, sources=[source for source, _ in sources]) for label, sources in items],
    )
    snapshot_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{snapshot_dir.name}-", dir=snapshot_dir.parent) as temporary:
        temporary_dir = Path(temporary)
        source_dir = temporary_dir / "sources"
        source_dir.mkdir()
        written: set[str] = set()
        for _, sources in items:
            for source, raw in sources:
                if source.sha256 not in written:
                    (temporary_dir / source.path).write_bytes(raw)
                    written.add(source.sha256)
        (temporary_dir / "governance-snapshot.json").write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
        temporary_dir.replace(snapshot_dir)
    return snapshot
