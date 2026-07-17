import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import yaml

from loop_apidoc.freshness.models import FreshnessInputError, SourceKind
from loop_apidoc.freshness.record import build_fingerprint, write_fingerprint


def _write_run_dir(tmp_path: Path, *, with_url: bool) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    (run / "openapi.yaml").write_text(
        yaml.safe_dump({"openapi": "3.1.0", "info": {"title": "X", "version": "2.3.0"}}),
        encoding="utf-8",
    )
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "spec.pdf").write_bytes(b"hello")
    manifest = {
        "sources_root": str(sources),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "local_sources": [{
            "relative_path": "spec.pdf", "mime_type": "application/pdf",
            "source_format": "pdf", "size_bytes": 5,
            "sha256": "5d41402abc4b2a76b9719d911017c592",
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "supported": True, "status": "pending",
        }],
        "url_sources": [],
    }
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if with_url:
        us = run / "url_sources"
        us.mkdir()
        cov = {
            "entry_url": "https://api.example.com/openapi.json",
            "confirmed_by_user": True,
            "expected": [{"url": "https://api.example.com/openapi.json", "source": "user"}],
            "results": [{"url": "https://api.example.com/openapi.json", "status": "fetched",
                         "file": "sources/openapi.json", "method": "direct"}],
        }
        (us / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")
    return run


def _client():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json", "etag": 'W/"v1"'},
                              content=b'{"openapi":"3.1.0","info":{"version":"2.3.0"}}')
    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


def test_build_local_only(tmp_path: Path):
    run = _write_run_dir(tmp_path, with_url=False)
    fp = build_fingerprint(run)
    assert fp.openapi_version == "2.3.0"
    assert len(fp.sources) == 1
    entry = fp.sources[0]
    assert entry.kind is SourceKind.LOCAL_FILE
    assert entry.id == "spec.pdf"
    assert entry.signal.sha256 == "5d41402abc4b2a76b9719d911017c592"


def test_build_with_url_source(tmp_path: Path):
    run = _write_run_dir(tmp_path, with_url=True)
    with _client() as c:
        fp = build_fingerprint(run, client=c)
    kinds = {e.kind for e in fp.sources}
    assert SourceKind.OPENAPI_URL in kinds and SourceKind.LOCAL_FILE in kinds
    url_entry = next(e for e in fp.sources if e.kind is SourceKind.OPENAPI_URL)
    assert url_entry.signal.version == "2.3.0"
    assert url_entry.signal.etag == 'W/"v1"'


def test_build_missing_openapi_raises(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(FreshnessInputError):
        build_fingerprint(tmp_path / "empty")


def test_write_fingerprint_refuses_overwrite(tmp_path: Path):
    run = _write_run_dir(tmp_path, with_url=False)
    fp = build_fingerprint(run)
    out = tmp_path / "fp.json"
    write_fingerprint(fp, out)
    with pytest.raises(FreshnessInputError):
        write_fingerprint(fp, out)
    write_fingerprint(fp, out, force=True)  # ok
    assert json.loads(out.read_text())["openapi_version"] == "2.3.0"
