from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

import pytest

from scripts.release import ReleaseError, prepare_release, tag_release


ROOT = Path(__file__).resolve().parents[1]


def _current_version() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return project["project"]["version"]


CURRENT_VERSION = _current_version()
_major, _minor, _patch = (int(part) for part in CURRENT_VERSION.split("."))
NEXT_VERSION = f"{_major}.{_minor + 1}.0"


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


def _write_current_release_notes(destination: Path) -> None:
    (destination / "docs" / f"RELEASE_NOTES_{CURRENT_VERSION}.md").write_text(
        "release notes", encoding="utf-8"
    )


def test_prepare_release_synchronizes_version_and_creates_notes(tmp_path: Path):
    _copy_release_files(tmp_path)
    calls: list[list[str]] = []

    def run(command: list[str], _cwd: Path) -> None:
        calls.append(command)

    prepare_release(tmp_path, NEXT_VERSION, "Adds reusable releases.", run=run)

    assert f'version = "{NEXT_VERSION}"' in (tmp_path / "pyproject.toml").read_text()
    assert f'__version__ = "{NEXT_VERSION}"' in (tmp_path / "loop_apidoc" / "__init__.py").read_text()
    assert f'"version": "{NEXT_VERSION}"' in (tmp_path / ".claude-plugin" / "plugin.json").read_text()
    assert f'version = "{NEXT_VERSION}"' in (tmp_path / "uv.lock").read_text()
    assert f"發行說明：[`{NEXT_VERSION}`](docs/RELEASE_NOTES_{NEXT_VERSION}.md)" in (tmp_path / "README.md").read_text()
    notes = (tmp_path / "docs" / f"RELEASE_NOTES_{NEXT_VERSION}.md").read_text()
    assert f"# loop-apidoc {NEXT_VERSION} release notes" in notes
    assert "Adds reusable releases." in notes
    assert calls == [["uv", "lock"]]


@pytest.mark.parametrize("version", [CURRENT_VERSION, "0.9.9", f"v{NEXT_VERSION}", "0.11"])
def test_prepare_release_rejects_invalid_or_non_increasing_version(tmp_path: Path, version: str):
    _copy_release_files(tmp_path)

    with pytest.raises(ReleaseError):
        prepare_release(tmp_path, version, "Summary", run=lambda *_: None)

    assert not (tmp_path / "docs" / f"RELEASE_NOTES_{version}.md").exists()
    assert f'version = "{CURRENT_VERSION}"' in (tmp_path / "pyproject.toml").read_text()


def test_prepare_release_refuses_existing_notes(tmp_path: Path):
    _copy_release_files(tmp_path)
    notes = tmp_path / "docs" / f"RELEASE_NOTES_{NEXT_VERSION}.md"
    notes.write_text("existing", encoding="utf-8")

    with pytest.raises(ReleaseError, match="already exists"):
        prepare_release(tmp_path, NEXT_VERSION, "Summary", run=lambda *_: None)


def test_tag_release_fetches_then_uses_package_version(tmp_path: Path):
    _copy_release_files(tmp_path)
    _write_current_release_notes(tmp_path)
    calls: list[list[str]] = []

    def run(command: list[str], _cwd: Path) -> None:
        calls.append(command)

    tag_release(tmp_path, f"loop-apidoc {CURRENT_VERSION}", dry_run=True, run=run)

    assert calls == [
        ["git", "fetch", "--tags", "origin"],
        [
            "npx", "tagsmith", "create", "--set-version", CURRENT_VERSION, "--push",
            "--message", f"loop-apidoc {CURRENT_VERSION}", "--dry-run",
        ],
    ]


def test_tag_release_pushes_main_before_publishing_tag(tmp_path: Path):
    _copy_release_files(tmp_path)
    _write_current_release_notes(tmp_path)
    calls: list[list[str]] = []

    def run(command: list[str], _cwd: Path) -> None:
        calls.append(command)

    tag_release(tmp_path, f"loop-apidoc {CURRENT_VERSION}", dry_run=False, run=run)

    assert calls == [
        ["gh", "auth", "status", "--hostname", "github.com"],
        ["git", "fetch", "--tags", "origin"],
        ["git", "push", "origin", "HEAD:main"],
        [
            "npx", "tagsmith", "create", "--set-version", CURRENT_VERSION, "--push",
            "--message", f"loop-apidoc {CURRENT_VERSION}",
        ],
        [
            "gh", "release", "create", f"v{CURRENT_VERSION}",
            "--verify-tag",
            "--title", f"loop-apidoc {CURRENT_VERSION}",
            "--notes-file", f"docs/RELEASE_NOTES_{CURRENT_VERSION}.md",
        ],
    ]
