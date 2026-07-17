import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.freshness.models import SourceFingerprint
from loop_apidoc.freshness.signals import hash_bytes

runner = CliRunner()


def _setup(tmp_path: Path, body: bytes, baseline_sha: str) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "spec.pdf").write_bytes(body)
    fp = SourceFingerprint(openapi_version="1.0.0",
                           sources=[{"id": "spec.pdf", "kind": "local_file", "signal": {"sha256": baseline_sha}}])
    (tmp_path / "a.json").write_text(fp.model_dump_json(), encoding="utf-8")
    wl = tmp_path / "freshness-watchlist.json"
    wl.write_text(json.dumps({"schema_version": 1,
                              "items": [{"label": "a", "fingerprint": "a.json", "sources": "src"}]}),
                  encoding="utf-8")
    return wl


def test_batch_unchanged_exit_0(tmp_path: Path):
    wl = _setup(tmp_path, b"hello", hash_bytes(b"hello"))
    res = runner.invoke(app, ["check-freshness-batch", "--watchlist", str(wl), "--json"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["verdict"] == "unchanged"


def test_batch_changed_exit_1(tmp_path: Path):
    wl = _setup(tmp_path, b"NEW", hash_bytes(b"hello"))
    res = runner.invoke(app, ["check-freshness-batch", "--watchlist", str(wl)])
    assert res.exit_code == 1


def test_batch_error_item_exit_2(tmp_path: Path):
    wl = tmp_path / "freshness-watchlist.json"
    wl.write_text(json.dumps({"schema_version": 1, "items": [{"label": "ghost", "fingerprint": "nope.json"}]}),
                  encoding="utf-8")
    res = runner.invoke(app, ["check-freshness-batch", "--watchlist", str(wl)])
    assert res.exit_code == 2


def test_batch_bad_watchlist_exit_2(tmp_path: Path):
    wl = tmp_path / "wl.json"
    wl.write_text("{not json", encoding="utf-8")
    res = runner.invoke(app, ["check-freshness-batch", "--watchlist", str(wl)])
    assert res.exit_code == 2


def test_batch_report_dir_writes_files(tmp_path: Path):
    wl = _setup(tmp_path, b"hello", hash_bytes(b"hello"))
    rd = tmp_path / "out"
    res = runner.invoke(app, ["check-freshness-batch", "--watchlist", str(wl), "--report-dir", str(rd)])
    assert res.exit_code == 0
    assert (rd / "freshness-scan.json").exists() and (rd / "freshness-scan.md").exists()
