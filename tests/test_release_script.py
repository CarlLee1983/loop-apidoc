from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.release import ReleaseError, prepare_release, tag_release


ROOT = Path(__file__).resolve().parents[1]


def _copy_release_files(destination: Path) -> None:
    for relative in [
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "README.en.md",
        "loop_apidoc/__init__.py",
        ".claude-plugin/plugin.json",
        "docs/introduction.html",
        "tests/test_plugin_manifest.py",
    ]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / relative, target)
    (destination / "docs").mkdir(exist_ok=True)


def test_prepare_release_synchronizes_version_and_creates_notes(tmp_path: Path):
    _copy_release_files(tmp_path)
    calls: list[list[str]] = []

    def run(command: list[str], _cwd: Path) -> None:
        calls.append(command)

    prepare_release(tmp_path, "0.11.0", "Adds reusable releases.", run=run)

    assert 'version = "0.11.0"' in (tmp_path / "pyproject.toml").read_text()
    assert '__version__ = "0.11.0"' in (tmp_path / "loop_apidoc/__init__.py").read_text()
    assert '"version": "0.11.0"' in (tmp_path / ".claude-plugin/plugin.json").read_text()
    assert 'version = "0.11.0"' in (tmp_path / "uv.lock").read_text()
    assert "發行說明：[`0.11.0`](docs/RELEASE_NOTES_0.11.0.md)" in (tmp_path / "README.md").read_text()
    notes = (tmp_path / "docs/RELEASE_NOTES_0.11.0.md").read_text()
    assert "# loop-apidoc 0.11.0 release notes" in notes
    assert "Adds reusable releases." in notes
    assert calls == [["uv", "lock"]]


@pytest.mark.parametrize("version", ["0.10.0", "0.9.9", "v0.11.0", "0.11"])
def test_prepare_release_rejects_invalid_or_non_increasing_version(tmp_path: Path, version: str):
    _copy_release_files(tmp_path)

    with pytest.raises(ReleaseError):
        prepare_release(tmp_path, version, "Summary", run=lambda *_: None)

    assert not (tmp_path / "docs" / f"RELEASE_NOTES_{version}.md").exists()
    assert 'version = "0.10.0"' in (tmp_path / "pyproject.toml").read_text()


def test_prepare_release_refuses_existing_notes(tmp_path: Path):
    _copy_release_files(tmp_path)
    notes = tmp_path / "docs/RELEASE_NOTES_0.11.0.md"
    notes.write_text("existing", encoding="utf-8")

    with pytest.raises(ReleaseError, match="already exists"):
        prepare_release(tmp_path, "0.11.0", "Summary", run=lambda *_: None)


def test_tag_release_fetches_then_uses_package_version(tmp_path: Path):
    _copy_release_files(tmp_path)
    calls: list[list[str]] = []

    def run(command: list[str], _cwd: Path) -> None:
        calls.append(command)

    tag_release(tmp_path, "loop-apidoc 0.10.0", dry_run=True, run=run)

    assert calls == [
        ["git", "fetch", "--tags", "origin"],
        [
            "npx", "tagsmith", "create", "--set-version", "0.10.0", "--push",
            "--message", "loop-apidoc 0.10.0", "--dry-run",
        ],
    ]


def test_tag_release_pushes_main_before_publishing_tag(tmp_path: Path):
    _copy_release_files(tmp_path)
    calls: list[list[str]] = []

    def run(command: list[str], _cwd: Path) -> None:
        calls.append(command)

    tag_release(tmp_path, "loop-apidoc 0.10.0", dry_run=False, run=run)

    assert calls == [
        ["git", "fetch", "--tags", "origin"],
        ["git", "push", "origin", "HEAD:main"],
        [
            "npx", "tagsmith", "create", "--set-version", "0.10.0", "--push",
            "--message", "loop-apidoc 0.10.0",
        ],
    ]
