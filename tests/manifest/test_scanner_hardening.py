from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.manifest.models import ProcessingStatus
from loop_apidoc.manifest.scanner import scan_sources


def _now() -> datetime:
    return datetime(2026, 6, 26, tzinfo=timezone.utc)


def test_broken_symlink_recorded_not_fatal(tmp_path: Path) -> None:
    (tmp_path / "good.md").write_text("# ok", encoding="utf-8")
    (tmp_path / "dangling.md").symlink_to(tmp_path / "missing-target.md")

    sources = scan_sources(tmp_path, scanned_at=_now())

    by_path = {s.relative_path: s for s in sources}
    assert by_path["good.md"].status is ProcessingStatus.PENDING
    assert by_path["dangling.md"].status is ProcessingStatus.UNREADABLE
    assert by_path["dangling.md"].sha256 == ""
    assert by_path["dangling.md"].supported is False


def test_symlink_escaping_root_is_unreadable(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    (root / "good.md").write_text("# ok", encoding="utf-8")

    # A secret outside the source root, surfaced via a symlink inside the root.
    secret = tmp_path / "secret.md"
    secret.write_text("TOP SECRET", encoding="utf-8")
    (root / "leak.md").symlink_to(secret)

    sources = scan_sources(root, scanned_at=_now())
    by_path = {s.relative_path: s for s in sources}

    assert by_path["good.md"].status is ProcessingStatus.PENDING
    leak = by_path["leak.md"]
    assert leak.status is ProcessingStatus.UNREADABLE
    assert leak.sha256 == ""
    assert leak.supported is False


def test_unreadable_file_recorded(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "secret.md"
    target.write_text("data", encoding="utf-8")

    import loop_apidoc.manifest.scanner as scanner

    real_hash = scanner.hash_file

    def boom(path: Path) -> str:
        if path.name == "secret.md":
            raise OSError("permission denied")
        return real_hash(path)

    monkeypatch.setattr(scanner, "hash_file", boom)

    sources = scan_sources(tmp_path, scanned_at=_now())
    secret = next(s for s in sources if s.relative_path == "secret.md")
    assert secret.status is ProcessingStatus.UNREADABLE
