# Repeatable Release Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a single, repeatable release preparation and tag workflow that keeps version metadata and git tags aligned.

**Architecture:** `scripts/release.py` owns local release preparation and delegates tag validation/creation to Tagsmith. `prepare` accepts the target version once and updates all owned metadata; `tag` reads the committed package version, pushes the committed `HEAD` to `origin/main`, then creates exactly that tag after fetching `origin` tags.

**Tech Stack:** Python 3.11 standard library, uv, npm, Tagsmith, pytest.

## Global Constraints

- Package version format is strict SemVer `MAJOR.MINOR.PATCH`, without a leading `v`.
- Git tags use the committed `.tagsmith.json` pattern `v{version}`.
- `prepare` never commits, tags, pushes, overwrites release notes, or operates on a dirty worktree.
- `tag` never chooses a bump level; it reads `pyproject.toml` and uses Tagsmith `--set-version`.

---

### Task 1: Lock the release-script contract with tests

**Files:**
- Create: `tests/test_release_script.py`
- Create: `scripts/release.py`

**Interfaces:**
- Produces `main(argv: list[str] | None = None) -> int`.
- `prepare --version X.Y.Z --summary TEXT` and `tag --message TEXT [--dry-run]` are the public commands.

- [ ] **Step 1: Write failing tests**

```python
def test_prepare_updates_all_versions_and_writes_notes(tmp_path):
    assert main(["prepare", "--version", "0.11.0", "--summary", "New CLI"]) == 0
    assert project_version(tmp_path) == "0.11.0"
    assert (tmp_path / "docs/RELEASE_NOTES_0.11.0.md").is_file()

def test_tag_uses_committed_package_version(monkeypatch):
    assert main(["tag", "--message", "Release", "--dry-run"]) == 0
    assert calls[-1] == ["npx", "tagsmith", "create", "--set-version", "0.10.0", "--push", "--message", "Release", "--dry-run"]
```

- [ ] **Step 2: Run the focused test**

Run: `uv run pytest -q tests/test_release_script.py`

Expected: FAIL because `scripts.release` does not yet expose `main`.

- [ ] **Step 3: Implement minimal release orchestration**

```python
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return prepare(args) if args.command == "prepare" else tag(args)
```

`prepare` validates clean git state and strict SemVer before writing, updates the
declared version locations, runs `uv lock`, then writes a new note. `tag` runs
`git fetch --tags origin`, pushes `HEAD:main` on a real run, and calls Tagsmith
with `--set-version`.

- [ ] **Step 4: Re-run focused tests**

Run: `uv run pytest -q tests/test_release_script.py`

Expected: PASS.

### Task 2: Make the release entry points discoverable and CI-safe

**Files:**
- Modify: `package.json`
- Modify: `docs/RELEASE_CHECKLIST.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `tests/test_plugin_manifest.py`

**Interfaces:**
- Produces `npm run release:prepare -- --version X.Y.Z --summary TEXT`.
- Produces `npm run release:tag -- --message TEXT [--dry-run]`.

- [ ] **Step 1: Extend the failing configuration test**

```python
assert package["scripts"]["release:prepare"] == "uv run python scripts/release.py prepare"
assert package["scripts"]["release:tag"] == "uv run python scripts/release.py tag"
```

- [ ] **Step 2: Add npm scripts and documentation**

```json
"release:prepare": "uv run python scripts/release.py prepare",
"release:tag": "uv run python scripts/release.py tag"
```

Document the four explicit steps: prepare, review notes and validate, commit,
then tag. Keep `tag:create` as the low-level Tagsmith escape hatch.

- [ ] **Step 3: Run configuration and release-script tests**

Run: `uv run pytest -q tests/test_plugin_manifest.py tests/test_release_script.py`

Expected: PASS.

### Task 3: Validate the reusable workflow

**Files:**
- Verify only: all changed files

- [ ] **Step 1: Run a non-mutating tag dry run**

Run: `npm run release:tag -- --message "loop-apidoc 0.10.0" --dry-run`

Expected: Tagsmith reports that it would create and push `v0.10.0`, without a tag write.

- [ ] **Step 2: Run full project verification**

Run: `npm run tag:check && uv run ruff check . && uv run pytest --cov=loop_apidoc && uv run python scripts/quality_gate.py`

Expected: Tagsmith accepts every tag; Python suite meets 95% coverage; quality gate passes.

- [ ] **Step 3: Commit implementation**

```bash
git add .tagsmith.json package.json package-lock.json scripts/release.py tests/test_release_script.py \
  tests/test_plugin_manifest.py .github/workflows/ci.yml .gitignore README.md README.en.md \
  docs/RELEASE_CHECKLIST.md docs/superpowers/plans/2026-07-17-repeatable-release-workflow.md
git commit -m "feat: automate release preparation"
```
