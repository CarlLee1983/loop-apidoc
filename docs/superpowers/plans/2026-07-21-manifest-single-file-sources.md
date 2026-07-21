# Manifest Single-File Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the `manifest` command to accept one source file and emit a manifest containing only that file.

**Architecture:** Keep `build_manifest()` and `scan_sources()` directory-rooted. The CLI normalizes a file argument to its parent directory, builds the manifest through the existing path, then selects the entry whose relative path identifies the user-supplied file. Directory inputs follow the unchanged path.

**Tech Stack:** Python 3.11+, Typer, Pydantic v2, pytest.

## Global Constraints

- Apply the change only to `loop-apidoc manifest`; all other `--sources` commands remain directory-only.
- `Manifest.sources_root` for a file input is the file's parent directory.
- A file input produces exactly one `local_sources` item with the file's POSIX relative path.
- Preserve existing URL probing, exclusion, status, hashing, and directory-input semantics.
- Keep human-facing command documentation English-primary with Traditional-Chinese support.

---

## File Structure

- Modify `loop_apidoc/cli.py`: relax the manifest command's Typer path constraint and normalize a file input before calling the existing builder.
- Modify `tests/test_cli_manifest.py`: lock down single-file output and preserve the existing directory regression coverage.
- Modify `README.en.md`: document directory-or-file `--sources` input in the English manifest command reference.
- Modify `README.md`: add equivalent Traditional-Chinese wording.

### Task 1: Normalize a single-file manifest input

**Files:**
- Modify: `tests/test_cli_manifest.py`
- Modify: `loop_apidoc/cli.py:49-82`

**Interfaces:**
- Consumes: `manifest(sources: Path, url: list[str], exclude: list[str], output: Path | None) -> None`.
- Produces: `manifest` accepts either an existing readable file or directory and passes a directory root to `build_manifest()`.

- [ ] **Step 1: Write the failing CLI regression test**

Add this test after `test_manifest_command_writes_output` in `tests/test_cli_manifest.py`:

```python
def test_manifest_command_accepts_a_single_source_file(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    selected = sources / "guide.md"
    selected.write_text("selected", encoding="utf-8")
    (sources / "unselected.md").write_text("unselected", encoding="utf-8")

    result = runner.invoke(app, ["manifest", "--sources", str(selected)])

    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["sources_root"] == str(sources)
    assert [source["relative_path"] for source in data["local_sources"]] == ["guide.md"]
    assert data["local_sources"][0]["status"] == "pending"
```

- [ ] **Step 2: Run the new test to verify the current failure**

Run: `uv run pytest tests/test_cli_manifest.py::test_manifest_command_accepts_a_single_source_file -v`

Expected: FAIL because Typer rejects a file for `--sources`.

- [ ] **Step 3: Implement file normalization and manifest-entry selection**

Replace the `sources` option definition in `loop_apidoc/cli.py` with a path that accepts either kind, then normalize and filter immediately before/after the existing builder call:

```python
sources: Path = typer.Option(
    ...,
    "--sources",
    help="本機來源目錄或單一來源檔案",
    exists=True,
    file_okay=True,
    dir_okay=True,
    readable=True,
),
```

```python
sources_root = sources.parent if sources.is_file() else sources
selected_relative_path = (
    sources.relative_to(sources_root).as_posix() if sources.is_file() else None
)
result = build_manifest(
    sources_root=sources_root,
    urls=list(url),
    generated_at=generated_at,
    excludes=tuple(exclude),
)
if selected_relative_path is not None:
    result = result.model_copy(
        update={
            "local_sources": [
                source
                for source in result.local_sources
                if source.relative_path == selected_relative_path
            ]
        }
    )
```

Keep the existing output serialization unchanged. Do not change `build_manifest()` or `scan_sources()`.

- [ ] **Step 4: Run the focused manifest CLI test file**

Run: `uv run pytest tests/test_cli_manifest.py -v`

Expected: PASS, including the new file-input test and existing directory/exclusion tests.

- [ ] **Step 5: Commit the implementation and regression test**

```bash
git add loop_apidoc/cli.py tests/test_cli_manifest.py
git commit -m "feat(manifest): accept single source files"
```

### Task 2: Document `manifest --sources` input forms

**Files:**
- Modify: `README.en.md:187`
- Modify: `README.md:180`

**Interfaces:**
- Consumes: the single-file CLI behaviour from Task 1.
- Produces: bilingual command reference accurately states that `--sources` accepts a directory or one source file.

- [ ] **Step 1: Add English command guidance**

In `README.en.md`, replace the manifest command synopsis with:

```bash
uv run loop-apidoc manifest --sources ./sources-or-file [--url <URL> ...] [--output manifest.json]
```

Immediately below it, add:

```markdown
`--sources` accepts either a directory of local source files or one source file. When a file is supplied, its parent directory becomes `sources_root` and the manifest contains only that file.
```

- [ ] **Step 2: Add Traditional-Chinese command guidance**

In `README.md`, make the same synopsis replacement and add:

```markdown
`--sources` 可接受本機來源目錄或單一來源檔案；若提供檔案，系統會以其父目錄作為 `sources_root`，且 manifest 僅包含該檔案。
```

- [ ] **Step 3: Verify documentation and the focused test suite**

Run: `git diff --check && uv run pytest tests/test_cli_manifest.py -v`

Expected: no whitespace errors and all manifest CLI tests PASS.

- [ ] **Step 4: Commit the documentation**

```bash
git add README.en.md README.md
git commit -m "docs: clarify manifest source file support"
```

## Final Verification

- [ ] Run `uv run pytest tests/test_cli_manifest.py tests/manifest -v` and confirm all tests pass.
- [ ] Run `uv run ruff check loop_apidoc/cli.py tests/test_cli_manifest.py` and confirm no lint findings.
- [ ] Run `git status --short --branch` and confirm only intentional commits are present.
