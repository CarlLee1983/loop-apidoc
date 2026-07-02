# Correctness Batch 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the first batch of correctness issues: preserve unsupported preprocess inputs, surface unexpected score bugs, remove two diff false positives, and update the project docs that track those issues.

**Architecture:** Keep the fixes narrow and behavior-preserving outside the reported bugs. Add a typed `PreprocessResult` at the preprocess boundary, remove only the broad score exception handler, and adjust the pure diff comparator with focused guards and deterministic sorting.

**Tech Stack:** Python 3.11, Typer, Pydantic v2, pytest, existing `loop_apidoc.agentcli`, `loop_apidoc.cli`, and `loop_apidoc.diff` modules.

---

## File Structure

- Modify `loop_apidoc/agentcli/preprocess.py`: add frozen `PreprocessResult`, preserve all non-PDF/non-text files with byte-for-byte passthrough copying, and return stable relative output paths by category.
- Modify `loop_apidoc/cli.py`: update `preprocess` command output for categorized counts and passthrough notices; remove the broad `except Exception` branch from `assemble --score`.
- Modify `tests/test_cli_preprocess.py`: add direct `prepare_markdown` contract tests for passthrough bytes and result categorization; assert CLI summary and passthrough filenames.
- Modify `tests/test_cli_assemble.py`: change the score regression from swallowed `RuntimeError` to propagated `RuntimeError`, while preserving existing `ScoreInputError` behavior.
- Modify `loop_apidoc/diff/compare.py`: return early when schema type flips between object and non-object; sort provenance entries inside each target group before comparing.
- Modify `tests/diff/test_compare_openapi.py`: add object-to-scalar regression coverage asserting only one breaking schema finding and no property-removal noise.
- Modify `tests/diff/test_compare_supporting_artifacts.py`: add provenance reorder coverage asserting no finding, and content-change coverage remains intact.
- Modify `docs/PIPELINE_FOLLOWUPS.md`: mark resolved follow-up items 1, 2, 3, 4, and 5; keep items 6 and 7 open; close already-implemented deferred examples/oneOf notes; keep path-template parameter loss as an open edge.
- Modify `docs/ARCHITECTURE.md`: update the preprocess seam return type from `Path` to `PreprocessResult`.

## Task 1: Preserve Passthrough Inputs in Preprocess

**Files:**
- Modify: `loop_apidoc/agentcli/preprocess.py`
- Modify: `loop_apidoc/cli.py`
- Modify: `tests/test_cli_preprocess.py`

- [ ] **Step 1: Write failing preprocess tests**

Replace `tests/test_cli_preprocess.py` with:

```python
from __future__ import annotations

from pathlib import Path

import pymupdf
from typer.testing import CliRunner

from loop_apidoc.agentcli.preprocess import PreprocessResult, prepare_markdown
from loop_apidoc.cli import app

runner = CliRunner()


def test_prepare_markdown_returns_categorized_relative_paths_and_passthrough_bytes(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "notes.md").write_text("# Hello\nGET /ping", encoding="utf-8")
    docx_bytes = b"PK\x03\x04docx\x00\xff"
    json_bytes = b'{"openapi":"3.1.0"}\n'
    yaml_bytes = b"openapi: 3.1.0\n"
    (sources / "manual.docx").write_bytes(docx_bytes)
    (sources / "openapi.json").write_bytes(json_bytes)
    (sources / "openapi.yaml").write_bytes(yaml_bytes)
    out = tmp_path / "md"

    result = prepare_markdown(sources, out)

    assert isinstance(result, PreprocessResult)
    assert result.dest_dir == out
    assert result.converted == []
    assert result.copied == [Path("notes.md")]
    assert result.passthrough == [
        Path("manual.docx"),
        Path("openapi.json"),
        Path("openapi.yaml"),
    ]
    assert (out / "notes.md").read_text(encoding="utf-8") == "# Hello\nGET /ping"
    assert (out / "manual.docx").read_bytes() == docx_bytes
    assert (out / "openapi.json").read_bytes() == json_bytes
    assert (out / "openapi.yaml").read_bytes() == yaml_bytes


def test_preprocess_copies_text_sources(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "notes.md").write_text("# Hello\nGET /ping", encoding="utf-8")
    out = tmp_path / "md"

    res = runner.invoke(app, ["preprocess", "--sources", str(sources), "--out", str(out)])

    assert res.exit_code == 0
    assert (out / "notes.md").read_text(encoding="utf-8") == "# Hello\nGET /ping"
    assert "converted 0 / copied 1 / passthrough 0" in res.stdout


def test_preprocess_converts_pdf_to_markdown(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Payment API")
    doc.save(str(sources / "manual.pdf"))
    doc.close()
    out = tmp_path / "md"

    res = runner.invoke(app, ["preprocess", "--sources", str(sources), "--out", str(out)])

    assert res.exit_code == 0
    md = (out / "manual.md").read_text(encoding="utf-8")
    assert "Payment API" in md
    assert "<!-- page 1 -->" in md
    assert "converted 1 / copied 0 / passthrough 0" in res.stdout


def test_preprocess_cli_lists_passthrough_files(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "guide.docx").write_bytes(b"docx bytes")
    (sources / "contract.json").write_bytes(b'{"paths":{}}')
    out = tmp_path / "md"

    res = runner.invoke(app, ["preprocess", "--sources", str(sources), "--out", str(out)])

    assert res.exit_code == 0
    assert "converted 0 / copied 0 / passthrough 2" in res.stdout
    assert "passthrough guide.docx (not converted; agent must read source format)" in res.stdout
    assert "passthrough contract.json (not converted; agent must read source format)" in res.stdout
    assert (out / "guide.docx").read_bytes() == b"docx bytes"
    assert (out / "contract.json").read_bytes() == b'{"paths":{}}'
```

- [ ] **Step 2: Run failing preprocess tests**

Run:

```bash
uv run pytest tests/test_cli_preprocess.py -v
```

Expected: FAIL during import with `ImportError: cannot import name 'PreprocessResult'` or FAIL because unknown files are absent from `out`.

- [ ] **Step 3: Implement `PreprocessResult` and passthrough copying**

Edit `loop_apidoc/agentcli/preprocess.py` to:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf4llm

# Source formats we can flatten to markdown text for the agent to read. Other
# formats are copied byte-for-byte so no declared source silently disappears.
_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


@dataclass(frozen=True)
class PreprocessResult:
    dest_dir: Path
    converted: list[Path]
    copied: list[Path]
    passthrough: list[Path]


def pdf_to_markdown(pdf_path: Path) -> str:
    """Convert a PDF to GitHub-flavoured markdown, one page at a time, with page
    markers so the agent can cite pages. Unlike raw text extraction this
    preserves tables (as markdown tables) and heading structure — critical for
    faithfully recovering parameter tables into schemas. Reading this (~tens of K
    tokens) is far cheaper per query than re-parsing the PDF every time."""
    chunks = pymupdf4llm.to_markdown(
        str(pdf_path), page_chunks=True, show_progress=False
    )
    parts: list[str] = []
    for chunk in chunks:
        page_no = chunk["metadata"]["page_number"]
        parts.append(f"\n\n<!-- page {page_no} -->\n")
        parts.append(chunk["text"])
    return "".join(parts)


def prepare_markdown(sources_dir: Path, dest_dir: Path) -> PreprocessResult:
    """Convert PDFs to markdown and copy every other source into `dest_dir`.

    Returned paths are relative to `dest_dir`. The existing flat output naming
    and overwrite-on-name-collision behavior is intentionally preserved.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    converted: list[Path] = []
    copied: list[Path] = []
    passthrough: list[Path] = []

    for path in sorted(sources_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            relative = Path(f"{path.stem}.md")
            md = pdf_to_markdown(path)
            (dest_dir / relative).write_text(md, encoding="utf-8")
            converted.append(relative)
        elif suffix in _TEXT_SUFFIXES:
            relative = Path(path.name)
            (dest_dir / relative).write_text(
                path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
            )
            copied.append(relative)
        else:
            relative = Path(path.name)
            (dest_dir / relative).write_bytes(path.read_bytes())
            passthrough.append(relative)

    return PreprocessResult(
        dest_dir=dest_dir,
        converted=converted,
        copied=copied,
        passthrough=passthrough,
    )
```

- [ ] **Step 4: Update CLI preprocess output**

In `loop_apidoc/cli.py`, replace the body of `preprocess` after the import with:

```python
    result = prepare_markdown(sources, out)
    typer.echo(
        "已前處理 "
        f"converted {len(result.converted)} / "
        f"copied {len(result.copied)} / "
        f"passthrough {len(result.passthrough)} 於 {result.dest_dir}"
    )
    for relative in result.passthrough:
        typer.echo(
            f"passthrough {relative.as_posix()} "
            "(not converted; agent must read source format)"
        )
```

- [ ] **Step 5: Run preprocess tests**

Run:

```bash
uv run pytest tests/test_cli_preprocess.py -v
```

Expected: PASS, including `test_prepare_markdown_returns_categorized_relative_paths_and_passthrough_bytes`.

- [ ] **Step 6: Commit preprocess fix**

Run:

```bash
git add loop_apidoc/agentcli/preprocess.py loop_apidoc/cli.py tests/test_cli_preprocess.py
git commit -m "Preserve every declared preprocess source" \
  -m "Constraint: README declares Word and OpenAPI JSON/YAML as supported inputs, so preprocess must not drop unknown suffixes before extraction." \
  -m "Rejected: converting docx/json/yaml to markdown in this batch | outside the correctness-only scope." \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: Keep flat destination overwrite semantics unless a later spec explicitly changes collision handling." \
  -m "Tested: uv run pytest tests/test_cli_preprocess.py -v" \
  -m "Not-tested: real Word document semantic extraction; passthrough preserves bytes only."
```

## Task 2: Propagate Unexpected `assemble --score` Exceptions

**Files:**
- Modify: `loop_apidoc/cli.py`
- Modify: `tests/test_cli_assemble.py`

- [ ] **Step 1: Write failing score exception test**

In `tests/test_cli_assemble.py`, add `import pytest` below the existing imports:

```python
import pytest
```

Replace `test_assemble_score_failure_does_not_change_exit_code` with these two tests:

```python
def test_assemble_score_input_error_does_not_change_exit_code(tmp_path, monkeypatch):
    """Expected score input problems still degrade to score_error."""
    import loop_apidoc.score as _score_mod
    from loop_apidoc.score import ScoreInputError

    def _invalid_input(*_args, **_kwargs):
        raise ScoreInputError("missing score artifact")

    monkeypatch.setattr(_score_mod, "load_score_inputs", _invalid_input)

    sources, extraction, out = _setup(tmp_path)
    res = runner.invoke(app, [
        "assemble",
        "--sources", str(sources),
        "--extraction", str(extraction),
        "--output", str(out),
        "--score",
        "--json",
    ])

    assert res.exit_code in (0, 1)
    payload = json.loads(res.stdout)
    assert res.exit_code == (0 if payload["ok"] else 1)
    assert payload["score_error"] == "missing score artifact"
    assert "score" not in payload
    assert "score input error: missing score artifact" in res.stderr


def test_assemble_score_unexpected_exception_propagates(tmp_path, monkeypatch):
    """Unexpected scoring bugs must surface as tracebacks instead of score_error."""
    import loop_apidoc.score as _score_mod

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(_score_mod, "evaluate_score", _boom)

    sources, extraction, out = _setup(tmp_path)

    with pytest.raises(RuntimeError, match="boom"):
        runner.invoke(
            app,
            [
                "assemble",
                "--sources", str(sources),
                "--extraction", str(extraction),
                "--output", str(out),
                "--score",
                "--json",
            ],
            catch_exceptions=False,
        )
```

- [ ] **Step 2: Run failing assemble test**

Run:

```bash
uv run pytest tests/test_cli_assemble.py::test_assemble_score_unexpected_exception_propagates -v
```

Expected: FAIL because `RuntimeError` is swallowed and converted to a `score_error` JSON field.

- [ ] **Step 3: Remove only the broad exception handler**

In `loop_apidoc/cli.py`, inside the `assemble` command score block, replace:

```python
        except ScoreInputError as exc:
            score_error = str(exc)
            typer.echo(f"score input error: {exc}", err=True)
        except Exception as exc:
            score_error = f"score failed: {exc}"
            typer.echo(f"score failed: {exc}", err=True)
```

with:

```python
        except ScoreInputError as exc:
            score_error = str(exc)
            typer.echo(f"score input error: {exc}", err=True)
```

- [ ] **Step 4: Run targeted assemble tests**

Run:

```bash
uv run pytest tests/test_cli_assemble.py -v
```

Expected: PASS. Existing score success, no-score, loop, exit-code tests remain green, and `test_assemble_score_input_error_does_not_change_exit_code` proves the typed degradation path is unchanged.

- [ ] **Step 5: Commit score exception fix**

Run:

```bash
git add loop_apidoc/cli.py tests/test_cli_assemble.py
git commit -m "Expose unexpected scoring defects during assemble" \
  -m "Constraint: ScoreInputError is the only expected assemble score degradation path." \
  -m "Rejected: preserving score_error for arbitrary exceptions | it hides bugs in score evaluation and violates the correctness spec." \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: Add explicit typed exceptions for future recoverable score failures instead of broad catches." \
  -m "Tested: uv run pytest tests/test_cli_assemble.py -v" \
  -m "Not-tested: external CLI traceback formatting outside Typer CliRunner."
```

## Task 3: Suppress Object-to-Scalar Diff Noise

**Files:**
- Modify: `loop_apidoc/diff/compare.py`
- Modify: `tests/diff/test_compare_openapi.py`

- [ ] **Step 1: Write failing object-to-scalar diff test**

Append this test to `tests/diff/test_compare_openapi.py`:

```python
def test_object_to_scalar_schema_change_reports_only_schema_change():
    base = _doc()
    head = _doc()
    head["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "type": "string"
    }

    findings = _findings(base, head)
    target = "POST /payments responses.200.application/json"
    schema_changes = [
        finding
        for finding in findings
        if finding.location == target and finding.summary == "schema changed"
    ]
    property_removals = [
        finding
        for finding in findings
        if finding.location.startswith(f"{target}.") and finding.summary == "property removed"
    ]

    assert len(schema_changes) == 1
    assert schema_changes[0].impact is DiffImpact.BREAKING
    assert property_removals == []
```

- [ ] **Step 2: Run failing diff test**

Run:

```bash
uv run pytest tests/diff/test_compare_openapi.py::test_object_to_scalar_schema_change_reports_only_schema_change -v
```

Expected: FAIL because a `property removed` finding appears below the top-level `schema changed` finding.

- [ ] **Step 3: Add the object/non-object early return**

In `loop_apidoc/diff/compare.py`, add this helper below `_schema_signature`:

```python
def _is_object_schema(signature: Any) -> bool:
    return isinstance(signature, dict) and signature.get("type") == "object"
```

Then in `_compare_schema`, replace the existing `if base_sig != head_sig:` block with:

```python
    if base_sig != head_sig:
        findings.append(
            _finding(
                DiffImpact.BREAKING,
                area,
                location,
                "schema changed",
                base_sig,
                head_sig,
            )
        )
        if _is_object_schema(base_sig) != _is_object_schema(head_sig):
            return
```

- [ ] **Step 4: Run OpenAPI diff tests**

Run:

```bash
uv run pytest tests/diff/test_compare_openapi.py -v
```

Expected: PASS. Existing object-to-object property additions, removals, and required-field checks still run.

- [ ] **Step 5: Commit object-scalar diff fix**

Run:

```bash
git add loop_apidoc/diff/compare.py tests/diff/test_compare_openapi.py
git commit -m "Report schema shape flips without property noise" \
  -m "Constraint: object to non-object changes are already captured by the parent schema signature." \
  -m "Rejected: filtering property removed findings after collection | recursion would still produce misleading intermediate findings." \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: Keep object-to-object schema walks unchanged so granular property changes remain visible." \
  -m "Tested: uv run pytest tests/diff/test_compare_openapi.py -v" \
  -m "Not-tested: non-dict malformed schemas because _content_schemas only passes dict schemas."
```

## Task 4: Make Provenance Comparison Order-Insensitive

**Files:**
- Modify: `loop_apidoc/diff/compare.py`
- Modify: `tests/diff/test_compare_supporting_artifacts.py`

- [ ] **Step 1: Write failing provenance reorder test**

Append this test to `tests/diff/test_compare_supporting_artifacts.py`:

```python
def test_provenance_entry_reorder_is_not_reported():
    first = ProvenanceEntry(
        target="paths./payments.post",
        status=PlanItemStatus.SUPPORTED,
        manifest_source="manual-a.md",
        query_id="01",
    )
    second = ProvenanceEntry(
        target="paths./payments.post",
        status=PlanItemStatus.SUPPORTED,
        manifest_source="manual-b.md",
        query_id="02",
    )
    base = _artifacts(
        provenance=ProvenanceDocument(notebook_url="", entries=[first, second])
    )
    head = _artifacts(
        provenance=ProvenanceDocument(notebook_url="", entries=[second, first])
    )

    findings = build_diff_report(base, head).findings

    assert not [finding for finding in findings if finding.area == "provenance"]
```

- [ ] **Step 2: Run failing provenance reorder test**

Run:

```bash
uv run pytest tests/diff/test_compare_supporting_artifacts.py::test_provenance_entry_reorder_is_not_reported -v
```

Expected: FAIL with a `provenance changed` finding because list order differs.

- [ ] **Step 3: Sort entries inside `_provenance_map`**

In `loop_apidoc/diff/compare.py`, replace `_provenance_map` with:

```python
def _provenance_map(artifacts: RunArtifacts) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for entry in artifacts.provenance.entries:
        out.setdefault(entry.target, []).append(entry.model_dump(mode="json"))
    for target, entries in out.items():
        entries.sort(
            key=lambda entry: (
                str(entry.get("manifest_source", "")),
                str(entry.get("query_id", "")),
            )
        )
    return out
```

- [ ] **Step 4: Run supporting artifact diff tests**

Run:

```bash
uv run pytest tests/diff/test_compare_supporting_artifacts.py -v
```

Expected: PASS. `test_provenance_citation_change_is_source_only` still proves real provenance content changes report `DiffImpact.SOURCE_ONLY`.

- [ ] **Step 5: Commit provenance sort fix**

Run:

```bash
git add loop_apidoc/diff/compare.py tests/diff/test_compare_supporting_artifacts.py
git commit -m "Ignore semantic no-op provenance reordering" \
  -m "Constraint: provenance target groups can be emitted in different entry orders without changing source support." \
  -m "Rejected: sorting the full provenance document before grouping | target grouping already defines the comparison boundary." \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: Keep manifest_source and query_id in the sort key because they identify citation entries inside one target group." \
  -m "Tested: uv run pytest tests/diff/test_compare_supporting_artifacts.py -v" \
  -m "Not-tested: duplicate entries with identical manifest_source and query_id because equality still preserves duplicate counts."
```

## Task 5: Update Tracking Docs and Run Full Verification

**Files:**
- Modify: `docs/PIPELINE_FOLLOWUPS.md`
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Update `docs/ARCHITECTURE.md` preprocess seam**

In the data-flow table, replace:

```markdown
| 前處理(可選) | `prepare_markdown(sources_dir, dest_dir)` / `pdf_to_markdown(pdf_path)` | `<WORK>/sources_md/`(高保真 markdown) |
```

with:

```markdown
| 前處理(可選) | `prepare_markdown(sources_dir, dest_dir)` → `PreprocessResult` / `pdf_to_markdown(pdf_path)` | `<WORK>/sources_md/`(PDF 轉 markdown;文字檔複製;其他來源 passthrough) |
```

- [ ] **Step 2: Update `docs/PIPELINE_FOLLOWUPS.md` resolved/open status**

In section `## 8. Run Version Diff — Deferred Minor Findings`, change the heading to:

```markdown
## 8. Run Version Diff — Deferred Minor Findings — partially resolved (2026-07-02)
```

Replace the paragraph under `### Risk` with:

```markdown
Items 1, 4, and 5 were already resolved before the 2026-07-02 correctness batch.
This batch resolves items 2 and 3. Items 6 and 7 remain open as second-batch
cleanup and coverage work.
```

Replace the numbered list under `### Recommended Work` with:

```markdown
1. **Resolved (2026-07-02 health check): Loader schema-mismatch error omits the file.**
   Bad provenance/validation/manifest parse paths now identify the offending
   artifact.
2. **Resolved (2026-07-02 correctness batch 1): `compare.py` object→scalar schema
   change double-reports.** Object/non-object flips now stop after the parent
   `schema changed` finding.
3. **Resolved (2026-07-02 correctness batch 1): `_provenance_map` compares entry
   lists by ordered position.** Entries are sorted inside each target group by
   `(manifest_source, query_id)` before comparison.
4. **Resolved (2026-07-02 health check): `_issue_key` excludes `suggested_fix`.**
   The issue key now includes remediation text so source-only validation changes
   are visible.
5. **Resolved (2026-07-02 health check): Integration key-collision on name-less
   items.** Duplicate unnamed items are disambiguated instead of overwritten.
6. **Open for correctness batch 2: CLI summary key access.** `cli.py` still uses
   literal `report.summary['breaking']` style lookups; replacing these with
   `.get(k, 0)` remains defensive cleanup.
7. **Open for correctness batch 2: Coverage gaps.** Remaining logic coverage:
   `info.title` CHANGED; property-no-longer-required CHANGED;
   removed-component-schema CHANGED; callbacks core-field
   (`verification`/`expected_response`) → BREAKING; validation-issue-removed →
   SOURCE_ONLY; strengthen `test_response_schema_type_change_is_breaking`
   location assertion from substring `in` to exact equality.
```

After the section's acceptance criteria, add:

```markdown
### Later Correctness Ledger

- **Resolved (2026-07-02 health check): examples encoding consistency.**
- **Resolved (2026-07-02 health check): generator native oneOf/discriminator.**
- **Open edge:** path parameters absent from the URL template can still be silently
  dropped; keep this for a later correctness batch with focused fixtures.
```

- [ ] **Step 3: Run docs grep checks**

Run:

```bash
rg -n "prepare_markdown\\(sources_dir, dest_dir\\)|object→scalar|_provenance_map|examples encoding|oneOf/discriminator|path parameters" docs/ARCHITECTURE.md docs/PIPELINE_FOLLOWUPS.md
```

Expected: output includes the `PreprocessResult` seam, resolved item 2, resolved item 3, resolved examples/oneOf ledger entries, and the open path-parameter edge.

- [ ] **Step 4: Run targeted regression suite**

Run:

```bash
uv run pytest \
  tests/test_cli_preprocess.py \
  tests/test_cli_assemble.py \
  tests/diff/test_compare_openapi.py \
  tests/diff/test_compare_supporting_artifacts.py \
  -v
```

Expected: PASS.

- [ ] **Step 5: Run full project verification**

Run:

```bash
uv run pytest
uv run ruff check .
```

Expected: both commands PASS. If `ruff` reports formatting or lint issues in touched files, fix those exact issues and rerun `uv run ruff check .`.

- [ ] **Step 6: Commit docs and verification cleanup**

Run:

```bash
git add docs/ARCHITECTURE.md docs/PIPELINE_FOLLOWUPS.md
git commit -m "Close correctness batch follow-up records" \
  -m "Constraint: implementation changes resolved tracked correctness findings and the architecture seam changed type." \
  -m "Rejected: clearing all deferred diff items | CLI summary hardening and extra coverage remain second-batch work." \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: Keep the path-template parameter-loss edge visible until a dedicated fixture and fix land." \
  -m "Tested: uv run pytest; uv run ruff check ." \
  -m "Not-tested: rendered HTML docs because only markdown tracking files changed."
```

## Final Verification Checklist

- [ ] `uv run pytest tests/test_cli_preprocess.py -v` passes.
- [ ] `uv run pytest tests/test_cli_assemble.py -v` passes.
- [ ] `uv run pytest tests/diff/test_compare_openapi.py -v` passes.
- [ ] `uv run pytest tests/diff/test_compare_supporting_artifacts.py -v` passes.
- [ ] `uv run pytest` passes.
- [ ] `uv run ruff check .` passes.
- [ ] `git status --short` shows only intentional changes or a clean tree after commits.

## Self-Review

- Spec coverage: Task 1 covers passthrough bytes, categorized `PreprocessResult`, CLI summary, and existing PDF/text behavior. Task 2 covers `ScoreInputError` preservation by keeping existing score tests and unexpected exception propagation. Task 3 covers object-to-scalar single breaking finding. Task 4 covers provenance reorder no-op and preserves content-change reporting. Task 5 covers follow-up and architecture docs.
- Placeholder scan: this plan contains concrete files, commands, code snippets, expected failures, expected passes, and Lore-format commit commands.
- Type consistency: `PreprocessResult.dest_dir`, `converted`, `copied`, and `passthrough` names match every test, CLI use, and architecture update. Diff tests use existing `DiffImpact` enum identity style.
