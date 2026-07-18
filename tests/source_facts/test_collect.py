"""事實蒐集是本套件唯一的檔案 I/O 出口。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.source_facts.collect import collect_facts

_TS = datetime(2026, 1, 1, tzinfo=UTC)

DOC = """
## Games

`GET /games`

| Name | Type |
| --- | --- |
| provider | string |
"""


def _manifest(root: Path):
    return build_manifest(sources_root=root, urls=[], generated_at=_TS)


def test_scans_markdown_sources_named_by_the_manifest(tmp_path: Path) -> None:
    (tmp_path / "api.md").write_text(DOC, encoding="utf-8")
    index = collect_facts(tmp_path, _manifest(tmp_path))
    assert [(e.method, e.path) for e in index.all_endpoints()] == [("GET", "/games")]
    assert index.sources[0].relative_path == "api.md"


def test_non_markdown_sources_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    index = collect_facts(tmp_path, _manifest(tmp_path))
    assert index.all_endpoints() == []


def test_unreadable_sources_do_not_abort_the_scan(tmp_path: Path) -> None:
    (tmp_path / "ok.md").write_text(DOC, encoding="utf-8")
    (tmp_path / "broken.md").write_bytes(b"\xff\xfe\x00binary")
    index = collect_facts(tmp_path, _manifest(tmp_path))
    assert [(e.method, e.path) for e in index.all_endpoints()] == [("GET", "/games")]


def test_no_sources_yields_an_empty_index(tmp_path: Path) -> None:
    assert collect_facts(tmp_path, _manifest(tmp_path)).all_endpoints() == []
