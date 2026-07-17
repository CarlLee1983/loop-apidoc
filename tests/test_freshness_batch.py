import json
from pathlib import Path


from loop_apidoc.freshness.models import (
    BatchItemStatus,
    FreshnessVerdict,
    SourceFingerprint,
    Watchlist,
    WatchlistItem,
)
from loop_apidoc.freshness.batch import load_watchlist, scan_watchlist
from loop_apidoc.freshness.signals import hash_bytes


def _local_fp_file(dir_: Path, name: str, sha: str) -> Path:
    fp = SourceFingerprint(
        openapi_version="1.0.0",
        sources=[{"id": "spec.pdf", "kind": "local_file", "signal": {"sha256": sha}}],
    )
    p = dir_ / name
    p.write_text(fp.model_dump_json(indent=2), encoding="utf-8")
    return p


def _write_watchlist(dir_: Path, items: list[dict]) -> Path:
    p = dir_ / "freshness-watchlist.json"
    p.write_text(json.dumps({"schema_version": 1, "items": items}), encoding="utf-8")
    return p


def test_load_watchlist_fail_loud(tmp_path: Path):
    import pytest
    from loop_apidoc.freshness.models import FreshnessInputError
    with pytest.raises(FreshnessInputError):
        load_watchlist(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(FreshnessInputError):
        load_watchlist(bad)


def test_scan_all_unchanged(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "spec.pdf").write_bytes(b"hello")
    _local_fp_file(tmp_path, "a.json", hash_bytes(b"hello"))
    wl = Watchlist(items=[WatchlistItem(label="a", fingerprint="a.json", sources="src")])
    report = scan_watchlist(wl, base_dir=tmp_path)
    assert report.verdict is FreshnessVerdict.UNCHANGED
    assert report.total == 1 and report.unchanged_count == 1
    assert report.items[0].status is BatchItemStatus.UNCHANGED


def test_scan_one_changed_is_1(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "spec.pdf").write_bytes(b"NEW")
    _local_fp_file(tmp_path, "a.json", hash_bytes(b"hello"))
    wl = Watchlist(items=[WatchlistItem(label="a", fingerprint="a.json", sources="src")])
    report = scan_watchlist(wl, base_dir=tmp_path)
    assert report.verdict is FreshnessVerdict.CHANGED
    assert report.changed_count == 1
    assert "hash changed" in (report.items[0].reason or "")


def test_scan_missing_fingerprint_is_error_and_2(tmp_path: Path):
    wl = Watchlist(items=[WatchlistItem(label="ghost", fingerprint="nope.json")])
    report = scan_watchlist(wl, base_dir=tmp_path)
    assert report.items[0].status is BatchItemStatus.ERROR
    assert report.verdict is FreshnessVerdict.INCONCLUSIVE  # error aggregates to inconclusive
    assert report.attention_count == 1


def test_scan_changed_dominates_error(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "spec.pdf").write_bytes(b"NEW")
    _local_fp_file(tmp_path, "a.json", hash_bytes(b"hello"))
    wl = Watchlist(items=[
        WatchlistItem(label="a", fingerprint="a.json", sources="src"),
        WatchlistItem(label="ghost", fingerprint="nope.json"),
    ])
    report = scan_watchlist(wl, base_dir=tmp_path)
    assert report.verdict is FreshnessVerdict.CHANGED  # changed dominates
    assert report.changed_count == 1 and report.attention_count == 1


def test_scan_relative_paths_resolved_against_base_dir(tmp_path: Path):
    sub = tmp_path / "watch"
    sub.mkdir()
    src = sub / "src"
    src.mkdir()
    (src / "spec.pdf").write_bytes(b"hello")
    _local_fp_file(sub, "a.json", hash_bytes(b"hello"))
    wl = Watchlist(items=[WatchlistItem(label="a", fingerprint="a.json", sources="src")])
    report = scan_watchlist(wl, base_dir=sub)
    assert report.items[0].status is BatchItemStatus.UNCHANGED
