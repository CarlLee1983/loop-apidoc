"""Prepare a synchronized release version and create its Tagsmith tag."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
RunCommand = Callable[[list[str], Path], None]


class ReleaseError(ValueError):
    """The requested release cannot be safely prepared or tagged."""


def _run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = _SEMVER.fullmatch(value)
    if not match:
        raise ReleaseError("version must be strict SemVer MAJOR.MINOR.PATCH")
    return tuple(int(part) for part in match.groups())


def _package_version(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, flags=re.MULTILINE)
    if not match:
        raise ReleaseError("pyproject.toml has no project version")
    return match.group(1)


def _replace(path: Path, pattern: str, replacement: str, *, flags: int = 0) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, flags=flags)
    if count != 1:
        raise ReleaseError(f"expected one version location in {path}")
    path.write_text(updated, encoding="utf-8")


def _update_versions(root: Path, current: str, target: str) -> None:
    _replace(root / "pyproject.toml", r'^version = "[^"]+"$', f'version = "{target}"', flags=re.MULTILINE)
    _replace(root / "loop_apidoc/__init__.py", r'^__version__ = "[^"]+"$', f'__version__ = "{target}"', flags=re.MULTILINE)
    _replace(root / ".claude-plugin/plugin.json", r'"version": "[^"]+"', f'"version": "{target}"')
    _replace(
        root / "uv.lock",
        r'(\[\[package\]\]\nname = "loop-apidoc"\nversion = ")[^"]+(")',
        rf'\g<1>{target}\g<2>',
    )
    _replace(
        root / "README.md",
        r'(發行說明：\[`)\d+\.\d+\.\d+(`\]\(docs/RELEASE_NOTES_)\d+\.\d+\.\d+(\.md\))',
        rf'\g<1>{target}\g<2>{target}\g<3>',
    )
    _replace(
        root / "README.en.md",
        r'(Release notes: \[`)\d+\.\d+\.\d+(`\]\(docs/RELEASE_NOTES_)\d+\.\d+\.\d+(\.md\))',
        rf'\g<1>{target}\g<2>{target}\g<3>',
    )
    _replace(root / "docs/introduction.html", r'loop-apidoc v\d+\.\d+\.\d+', f"loop-apidoc v{target}")
    test_path = root / "tests/test_plugin_manifest.py"
    test_text = test_path.read_text(encoding="utf-8")
    if current not in test_text:
        raise ReleaseError("version test does not name the current version")
    test_path.write_text(test_text.replace(current, target), encoding="utf-8")


def _notes_text(version: str, summary: str) -> str:
    return f"""# loop-apidoc {version} release notes

Release date: {date.today().isoformat()}

## Summary

{summary}

## Changed

- Describe the user-facing changes in this release.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
"""


def prepare_release(root: Path, version: str, summary: str, *, run: RunCommand = _run) -> None:
    current = _package_version(root)
    if _version_tuple(version) <= _version_tuple(current):
        raise ReleaseError(f"version {version} must be greater than current {current}")
    notes_path = root / "docs" / f"RELEASE_NOTES_{version}.md"
    if notes_path.exists():
        raise ReleaseError(f"release notes already exists: {notes_path}")

    _update_versions(root, current, version)
    run(["uv", "lock"], root)
    notes_path.write_text(_notes_text(version, summary), encoding="utf-8")


def tag_release(root: Path, message: str, *, dry_run: bool, run: RunCommand = _run) -> None:
    version = _package_version(root)
    _version_tuple(version)
    command = [
        "npx", "tagsmith", "create", "--set-version", version, "--push",
        "--message", message,
    ]
    if dry_run:
        command.append("--dry-run")
    run(["git", "fetch", "--tags", "origin"], root)
    run(command, root)


def _require_clean_worktree(root: Path) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True,
        capture_output=True, text=True,
    )
    if result.stdout:
        raise ReleaseError("worktree must be clean")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="synchronize release metadata")
    prepare.add_argument("--version", required=True)
    prepare.add_argument("--summary", required=True)
    tag = commands.add_parser("tag", help="create the package version's Tagsmith tag")
    tag.add_argument("--message", required=True)
    tag.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        _require_clean_worktree(ROOT)
        if args.command == "prepare":
            prepare_release(ROOT, args.version, args.summary)
        else:
            tag_release(ROOT, args.message, dry_run=args.dry_run)
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"release error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
