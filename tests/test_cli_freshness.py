import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.freshness.models import SourceFingerprint
from loop_apidoc.freshness.signals import hash_bytes

runner = CliRunner()


def _local_fingerprint(tmp_path: Path, sha: str) -> Path:
    fp = SourceFingerprint(
        openapi_version="2.3.0",
        sources=[{"id": "spec.pdf", "kind": "local_file", "signal": {"sha256": sha}}],
    )
    out = tmp_path / "fp.json"
    out.write_text(fp.model_dump_json(indent=2), encoding="utf-8")
    return out


def test_check_freshness_unchanged_exit_0(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "spec.pdf").write_bytes(b"hello")
    fp = _local_fingerprint(tmp_path, hash_bytes(b"hello"))
    result = runner.invoke(app, ["check-freshness", "--fingerprint", str(fp),
                                 "--sources", str(sources), "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["verdict"] == "unchanged"


def test_check_freshness_changed_exit_1(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "spec.pdf").write_bytes(b"CHANGED")
    fp = _local_fingerprint(tmp_path, hash_bytes(b"hello"))
    result = runner.invoke(app, ["check-freshness", "--fingerprint", str(fp),
                                 "--sources", str(sources)])
    assert result.exit_code == 1


def test_check_freshness_inconclusive_exit_2(tmp_path: Path):
    fp = _local_fingerprint(tmp_path, hash_bytes(b"hello"))  # no --sources
    result = runner.invoke(app, ["check-freshness", "--fingerprint", str(fp)])
    assert result.exit_code == 2


def test_check_freshness_bad_fingerprint_exit_2(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = runner.invoke(app, ["check-freshness", "--fingerprint", str(bad)])
    assert result.exit_code == 2


def test_record_fingerprint_writes_and_refuses_overwrite(tmp_path: Path, monkeypatch):
    # Build a minimal run-dir (local-only, no network).
    import yaml
    from datetime import datetime, timezone
    run = tmp_path / "run"
    run.mkdir()
    run.joinpath("openapi.yaml").write_text(
        yaml.safe_dump({"openapi": "3.1.0", "info": {"version": "2.3.0"}}), encoding="utf-8")
    manifest = {
        "sources_root": "s", "generated_at": datetime.now(timezone.utc).isoformat(),
        "local_sources": [], "url_sources": [],
    }
    run.joinpath("manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "fp.json"
    r1 = runner.invoke(app, ["record-fingerprint", "--run-dir", str(run), "--output", str(out)])
    assert r1.exit_code == 0 and out.exists()
    r2 = runner.invoke(app, ["record-fingerprint", "--run-dir", str(run), "--output", str(out)])
    assert r2.exit_code == 2  # refuses overwrite
