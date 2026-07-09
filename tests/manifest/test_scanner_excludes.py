from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.manifest.models import ProcessingStatus
from loop_apidoc.manifest.scanner import scan_sources

_AT = datetime(2026, 7, 9, tzinfo=timezone.utc)


def _scan(root: Path, **kw):
    return {s.relative_path: s for s in scan_sources(root, scanned_at=_AT, **kw)}


def test_readme_is_recorded_as_ignored_not_a_source(tmp_path: Path):
    """目錄說明檔不該取得「來源證據」的地位，但要看得見它被略過。"""
    (tmp_path / "README.md").write_text("這個資料夾放原始文件", encoding="utf-8")
    (tmp_path / "spec.md").write_text("# API", encoding="utf-8")

    sources = _scan(tmp_path)

    assert sources["README.md"].status is ProcessingStatus.IGNORED
    assert sources["README.md"].supported is False
    assert sources["spec.md"].status is ProcessingStatus.PENDING


def test_default_ignores_cover_license_and_changelog(tmp_path: Path):
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# 1.0", encoding="utf-8")

    sources = _scan(tmp_path)

    assert sources["LICENSE"].status is ProcessingStatus.IGNORED
    assert sources["CHANGELOG.md"].status is ProcessingStatus.IGNORED


def test_explicit_excludes_add_to_defaults(tmp_path: Path):
    (tmp_path / "notes.md").write_text("scratch", encoding="utf-8")
    (tmp_path / "spec.md").write_text("# API", encoding="utf-8")

    sources = _scan(tmp_path, excludes=("notes.*",))

    assert sources["notes.md"].status is ProcessingStatus.IGNORED
    assert sources["spec.md"].status is ProcessingStatus.PENDING


def test_exclude_matches_nested_relative_path(tmp_path: Path):
    nested = tmp_path / "vendor"
    nested.mkdir()
    (nested / "spec.md").write_text("# API", encoding="utf-8")

    sources = _scan(tmp_path, excludes=("vendor/*",))

    assert sources["vendor/spec.md"].status is ProcessingStatus.IGNORED


def test_ignored_file_is_not_hashed(tmp_path: Path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8")

    assert _scan(tmp_path)["README.md"].sha256 == ""
