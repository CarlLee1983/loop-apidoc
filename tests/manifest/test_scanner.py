from __future__ import annotations

from pathlib import Path

from loop_apidoc.manifest.models import ProcessingStatus, SourceFormat
from loop_apidoc.manifest.scanner import hash_file, scan_sources


def test_hash_file_matches_known_value(tmp_path: Path):
    target = tmp_path / "x.bin"
    target.write_bytes(b"abc")
    # SHA-256 of b"abc"
    assert hash_file(target) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_scan_classifies_and_dedupes(tmp_path: Path, fixed_now):
    (tmp_path / "a.md").write_text("same", encoding="utf-8")
    (tmp_path / "b.md").write_text("same", encoding="utf-8")  # duplicate content
    (tmp_path / "notes.txt").write_text("unsupported", encoding="utf-8")

    sources = scan_sources(tmp_path, scanned_at=fixed_now)
    by_path = {s.relative_path: s for s in sources}

    assert by_path["a.md"].status is ProcessingStatus.PENDING
    assert by_path["a.md"].supported is True
    assert by_path["b.md"].status is ProcessingStatus.DUPLICATE
    assert by_path["b.md"].duplicate_of == "a.md"
    assert by_path["a.md"].sha256 == by_path["b.md"].sha256
    assert by_path["notes.txt"].status is ProcessingStatus.UNSUPPORTED
    assert by_path["notes.txt"].supported is False
    assert by_path["notes.txt"].source_format is SourceFormat.UNKNOWN
    assert by_path["a.md"].scanned_at == fixed_now


def test_scan_records_nested_relative_paths(tmp_path: Path, fixed_now):
    nested = tmp_path / "api" / "v1"
    nested.mkdir(parents=True)
    (nested / "openapi.yaml").write_text("openapi: 3.1.0", encoding="utf-8")

    sources = scan_sources(tmp_path, scanned_at=fixed_now)

    assert len(sources) == 1
    assert sources[0].relative_path == "api/v1/openapi.yaml"
    assert sources[0].source_format is SourceFormat.OPENAPI_YAML
    assert sources[0].size_bytes == len(b"openapi: 3.1.0")
