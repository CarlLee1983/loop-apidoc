# Score-Gated Improvement Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, pure `loop_verdict()` that turns a completed run's score into a `converged`/`plateau`/`exhausted`/`continue` decision, surface it in `assemble --score --json`, and rewire the skill's correction loop to iterate toward a score target instead of stopping at validation pass.

**Architecture:** A new pure module `loop_apidoc/score/loop.py` classifies score findings into reducible (an agent re-read can fix) vs irreducible (fail-closed / source-silent), then applies a fixed-precedence state machine to decide whether the agent should keep correcting. The CLI computes the verdict after scoring and emits a `loop` block; the agent (driven by SKILL.md prose) actuates re-reads. No file I/O in `loop.py`; no change to validation's gate or assemble's exit code.

**Tech Stack:** Python >=3.11, pydantic v2, typer, pytest, `typer.testing.CliRunner`. Managed with `uv` (no pip).

## Global Constraints

- Python `>=3.11`; managed with `uv` — run tests via `uv run pytest`, lint via `uv run ruff check .`.
- `loop.py` is a **pure module**: no file I/O, no subprocess, no network (package-boundary rule — only `generate/`, `run/`, `preparation/report.py`, `score/report.py`, `diff/report.py` write files).
- Prefer immutable patterns; return new values.
- The score **never** changes validation pass/fail or the assemble exit code. `assemble` exit stays `0` on `ok`, `1` on validation FAIL, `2` on input/collision — regardless of verdict.
- Fail-closed / irreducible findings are **never** auto-fixed to raise the score.
- Verdict precedence (first match wins): `converged` (curr≥target) → `exhausted` (round≥max) → `plateau` (no reducible findings) → `plateau` (prev not None and curr≤prev) → `continue`.
- Reducible = **error**-severity `OPENAPI_INVALID` / `OUTPUT_MISMATCH` / `REQUIRED_INFO_MISSING` / `SOURCE_UNVERIFIED`. Everything else (all warnings, `SOURCE_CONFLICT`, `UNSUPPORTED_ASSERTION`) is irreducible.
- Commit messages follow `<type>: [<scope>] <subject>`; scope is `score`.
- SKILL.md and design/plan docs are English; generated product output stays zh-TW.

---

### Task 1: Finding classification + loop enum (`score/loop.py`)

The pure split of score findings into reducible vs irreducible. This is the invariant boundary: it decides which findings the loop may try to fix.

**Files:**
- Create: `loop_apidoc/score/loop.py`
- Test: `tests/score/test_loop.py`

**Interfaces:**
- Consumes: `ScoreFinding` from `loop_apidoc/score/models.py` (fields: `code: str`, `severity: str`, `category: ScoreCategory`, `blocking: bool`, `score_impact: int`, `location`/`evidence`/`suggested_fix: str`); `IssueCode`, `Severity` from `loop_apidoc/validate/models.py`.
- Produces: `LoopVerdict` (str enum: `converged`/`plateau`/`exhausted`/`continue`); `classify_findings(findings: list[ScoreFinding]) -> tuple[list[ScoreFinding], list[ScoreFinding]]` returning `(reducible, irreducible)` preserving input order.

- [ ] **Step 1: Write the failing test**

Create `tests/score/test_loop.py`:

```python
from __future__ import annotations

from loop_apidoc.score.loop import classify_findings
from loop_apidoc.score.models import ScoreCategory, ScoreFinding


def _finding(code: str, severity: str) -> ScoreFinding:
    return ScoreFinding(
        code=code,
        severity=severity,
        location="loc",
        evidence="ev",
        suggested_fix="fix",
        category=ScoreCategory.COMPLETENESS,
        blocking=False,
        score_impact=10,
    )


def test_error_openapi_invalid_is_reducible():
    reducible, irreducible = classify_findings([_finding("OPENAPI_INVALID", "error")])
    assert len(reducible) == 1
    assert irreducible == []


def test_error_required_info_missing_is_reducible():
    reducible, irreducible = classify_findings(
        [_finding("REQUIRED_INFO_MISSING", "error")]
    )
    assert len(reducible) == 1
    assert irreducible == []


def test_error_output_mismatch_and_source_unverified_are_reducible():
    reducible, irreducible = classify_findings([
        _finding("OUTPUT_MISMATCH", "error"),
        _finding("SOURCE_UNVERIFIED", "error"),
    ])
    assert len(reducible) == 2
    assert irreducible == []


def test_source_conflict_error_is_irreducible():
    reducible, irreducible = classify_findings([_finding("SOURCE_CONFLICT", "error")])
    assert reducible == []
    assert len(irreducible) == 1


def test_unsupported_assertion_error_is_irreducible():
    reducible, irreducible = classify_findings(
        [_finding("UNSUPPORTED_ASSERTION", "error")]
    )
    assert reducible == []
    assert len(irreducible) == 1


def test_any_warning_is_irreducible():
    reducible, irreducible = classify_findings([
        _finding("REQUIRED_INFO_MISSING", "warning"),
        _finding("SOURCE_UNVERIFIED", "warning"),
        _finding("REVIEW_HTML_MISSING", "warning"),
    ])
    assert reducible == []
    assert len(irreducible) == 3


def test_order_is_preserved_within_buckets():
    reducible, irreducible = classify_findings([
        _finding("OPENAPI_INVALID", "error"),
        _finding("SOURCE_CONFLICT", "error"),
        _finding("OUTPUT_MISMATCH", "error"),
    ])
    assert [f.code for f in reducible] == ["OPENAPI_INVALID", "OUTPUT_MISMATCH"]
    assert [f.code for f in irreducible] == ["SOURCE_CONFLICT"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/score/test_loop.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'loop_apidoc.score.loop'`.

- [ ] **Step 3: Write minimal implementation**

Create `loop_apidoc/score/loop.py`:

```python
from __future__ import annotations

from enum import Enum

from loop_apidoc.score.models import ScoreFinding
from loop_apidoc.validate.models import IssueCode, Severity


class LoopVerdict(str, Enum):
    CONVERGED = "converged"
    PLATEAU = "plateau"
    EXHAUSTED = "exhausted"
    CONTINUE = "continue"


# Findings an agent re-read can plausibly resolve — only at error severity.
# Everything else (every warning is source-silent; SOURCE_CONFLICT and
# UNSUPPORTED_ASSERTION are always fail-closed) is irreducible and must never be
# auto-fixed to raise the score.
_REDUCIBLE_ERROR_CODES: frozenset[str] = frozenset({
    IssueCode.OPENAPI_INVALID.value,
    IssueCode.OUTPUT_MISMATCH.value,
    IssueCode.REQUIRED_INFO_MISSING.value,
    IssueCode.SOURCE_UNVERIFIED.value,
})


def _is_reducible(finding: ScoreFinding) -> bool:
    if finding.severity != Severity.ERROR.value:
        return False
    return finding.code in _REDUCIBLE_ERROR_CODES


def classify_findings(
    findings: list[ScoreFinding],
) -> tuple[list[ScoreFinding], list[ScoreFinding]]:
    """Split findings into (reducible, irreducible), preserving order."""
    reducible = [f for f in findings if _is_reducible(f)]
    irreducible = [f for f in findings if not _is_reducible(f)]
    return reducible, irreducible
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/score/test_loop.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/score/loop.py tests/score/test_loop.py
git commit -m "feat: [score] classify loop findings into reducible vs irreducible"
```

---

### Task 2: `loop_verdict()` state machine (`score/loop.py`)

The deterministic decision: given round metadata and findings, return the verdict + bucketed findings. This is what the CLI serializes and the agent reads.

**Files:**
- Modify: `loop_apidoc/score/loop.py` (append `LoopReport` + `loop_verdict`)
- Modify: `loop_apidoc/score/__init__.py` (export new public names)
- Test: `tests/score/test_loop.py` (append verdict tests)

**Interfaces:**
- Consumes: `classify_findings`, `LoopVerdict` from Task 1; `ScoreFinding` from `score/models.py`.
- Produces: `LoopReport` (pydantic model: `verdict: LoopVerdict`, `target: int`, `prev_score: int | None`, `curr_score: int`, `round_index: int`, `max_rounds: int`, `actionable: list[ScoreFinding]`, `irreducible: list[ScoreFinding]`); `loop_verdict(*, prev_score: int | None, curr_score: int, target: int, round_index: int, max_rounds: int, findings: list[ScoreFinding]) -> LoopReport`.

- [ ] **Step 1: Write the failing test**

Append to `tests/score/test_loop.py`:

```python
import pytest

from loop_apidoc.score.loop import LoopReport, LoopVerdict, loop_verdict


def _rim(severity: str = "error"):  # one reducible finding by default
    return [_finding("REQUIRED_INFO_MISSING", severity)]


def test_converged_when_at_or_above_target():
    report = loop_verdict(
        prev_score=80, curr_score=85, target=85,
        round_index=3, max_rounds=6, findings=_rim(),
    )
    assert report.verdict is LoopVerdict.CONVERGED


def test_converged_takes_precedence_on_final_round():
    report = loop_verdict(
        prev_score=80, curr_score=88, target=85,
        round_index=6, max_rounds=6, findings=[],
    )
    assert report.verdict is LoopVerdict.CONVERGED


def test_exhausted_when_round_cap_reached_below_target():
    report = loop_verdict(
        prev_score=70, curr_score=80, target=85,
        round_index=6, max_rounds=6, findings=_rim(),
    )
    assert report.verdict is LoopVerdict.EXHAUSTED


def test_plateau_when_no_reducible_findings():
    report = loop_verdict(
        prev_score=None, curr_score=70, target=85,
        round_index=1, max_rounds=6,
        findings=[_finding("SOURCE_CONFLICT", "error")],
    )
    assert report.verdict is LoopVerdict.PLATEAU
    assert report.actionable == []
    assert len(report.irreducible) == 1


def test_plateau_when_score_does_not_improve():
    report = loop_verdict(
        prev_score=80, curr_score=80, target=85,
        round_index=3, max_rounds=6, findings=_rim(),
    )
    assert report.verdict is LoopVerdict.PLATEAU


def test_continue_when_improving_with_actionable():
    report = loop_verdict(
        prev_score=70, curr_score=80, target=85,
        round_index=2, max_rounds=6, findings=_rim(),
    )
    assert report.verdict is LoopVerdict.CONTINUE
    assert len(report.actionable) == 1


def test_round1_empty_actionable_is_plateau():
    report = loop_verdict(
        prev_score=None, curr_score=80, target=85,
        round_index=1, max_rounds=6, findings=[],
    )
    assert report.verdict is LoopVerdict.PLATEAU


def test_report_carries_round_metadata():
    report = loop_verdict(
        prev_score=72, curr_score=80, target=85,
        round_index=2, max_rounds=6, findings=_rim(),
    )
    assert isinstance(report, LoopReport)
    assert (report.target, report.prev_score, report.curr_score) == (85, 72, 80)
    assert (report.round_index, report.max_rounds) == (2, 6)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"prev_score": None, "curr_score": 101, "target": 85, "round_index": 1, "max_rounds": 6},
        {"prev_score": None, "curr_score": 80, "target": 101, "round_index": 1, "max_rounds": 6},
        {"prev_score": -1, "curr_score": 80, "target": 85, "round_index": 1, "max_rounds": 6},
        {"prev_score": None, "curr_score": 80, "target": 85, "round_index": 0, "max_rounds": 6},
        {"prev_score": None, "curr_score": 80, "target": 85, "round_index": 1, "max_rounds": 0},
    ],
)
def test_out_of_range_inputs_raise(kwargs):
    with pytest.raises(ValueError):
        loop_verdict(findings=[], **kwargs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/score/test_loop.py -v`
Expected: FAIL — `ImportError: cannot import name 'loop_verdict'`.

- [ ] **Step 3: Write minimal implementation**

Append to `loop_apidoc/score/loop.py` (after `classify_findings`), and add the import line `from pydantic import BaseModel, Field` near the top:

```python
class LoopReport(BaseModel):
    verdict: LoopVerdict
    target: int = Field(ge=0, le=100)
    prev_score: int | None = Field(default=None, ge=0, le=100)
    curr_score: int = Field(ge=0, le=100)
    round_index: int = Field(ge=1)
    max_rounds: int = Field(ge=1)
    actionable: list[ScoreFinding] = Field(default_factory=list)
    irreducible: list[ScoreFinding] = Field(default_factory=list)


def loop_verdict(
    *,
    prev_score: int | None,
    curr_score: int,
    target: int,
    round_index: int,
    max_rounds: int,
    findings: list[ScoreFinding],
) -> LoopReport:
    """Decide whether the agent should keep correcting toward the score target.

    Precedence (first match wins): converged (curr>=target) -> exhausted
    (round>=max) -> plateau (no reducible findings) -> plateau (no improvement)
    -> continue. Pure: no I/O.
    """
    if not 0 <= curr_score <= 100:
        raise ValueError(f"curr_score out of range 0-100: {curr_score}")
    if not 0 <= target <= 100:
        raise ValueError(f"target out of range 0-100: {target}")
    if prev_score is not None and not 0 <= prev_score <= 100:
        raise ValueError(f"prev_score out of range 0-100: {prev_score}")
    if round_index < 1:
        raise ValueError(f"round_index must be >= 1: {round_index}")
    if max_rounds < 1:
        raise ValueError(f"max_rounds must be >= 1: {max_rounds}")

    reducible, irreducible = classify_findings(findings)

    if curr_score >= target:
        verdict = LoopVerdict.CONVERGED
    elif round_index >= max_rounds:
        verdict = LoopVerdict.EXHAUSTED
    elif not reducible:
        verdict = LoopVerdict.PLATEAU
    elif prev_score is not None and curr_score <= prev_score:
        verdict = LoopVerdict.PLATEAU
    else:
        verdict = LoopVerdict.CONTINUE

    return LoopReport(
        verdict=verdict,
        target=target,
        prev_score=prev_score,
        curr_score=curr_score,
        round_index=round_index,
        max_rounds=max_rounds,
        actionable=reducible,
        irreducible=irreducible,
    )
```

- [ ] **Step 4: Export the public names**

Edit `loop_apidoc/score/__init__.py`. Add these imports after the existing `from loop_apidoc.score.loader import load_score_inputs` line:

```python
from loop_apidoc.score.loop import (
    LoopReport,
    LoopVerdict,
    classify_findings,
    loop_verdict,
)
```

Add `"LoopReport"`, `"LoopVerdict"`, `"classify_findings"`, `"loop_verdict"` to the `__all__` list (keep it alphabetically grouped as the file already is).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/score/test_loop.py -v`
Expected: PASS (all Task 1 + Task 2 tests green).

Run: `uv run python -c "from loop_apidoc.score import loop_verdict, LoopReport, LoopVerdict, classify_findings; print('ok')"`
Expected: prints `ok` (package-root exports resolve).

- [ ] **Step 6: Commit**

```bash
git add loop_apidoc/score/loop.py loop_apidoc/score/__init__.py tests/score/test_loop.py
git commit -m "feat: [score] add loop_verdict state machine (threshold + plateau)"
```

---

### Task 3: Surface the `loop` block in `assemble --score --json`

Wire the verdict into the CLI: four new flags on `assemble`, and a `loop` block in the `--json` payload whenever `--score` produced a score.

**Files:**
- Modify: `loop_apidoc/cli.py` (the `assemble` command, ~lines 197-296)
- Test: `tests/test_cli_assemble.py` (append)

**Interfaces:**
- Consumes: `loop_verdict` from `loop_apidoc.score` (Task 2); `resolved_min_score`, `ScoreProfile` (already imported in `cli.py`).
- Produces: `assemble` CLI flags `--target-score`, `--prev-score`, `--round-index`, `--max-rounds`; a `loop` key in the `--json` payload with the `LoopReport` shape. Exit code unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_assemble.py`:

```python
def test_assemble_score_emits_loop_block(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--json", "--score",
        "--target-score", "85", "--round-index", "1", "--max-rounds", "6",
    ])
    assert res.exit_code in (0, 1)
    payload = json.loads(res.stdout)
    assert "score" in payload
    assert "loop" in payload
    loop = payload["loop"]
    assert loop["verdict"] in {"converged", "plateau", "exhausted", "continue"}
    assert loop["target"] == 85
    assert loop["round_index"] == 1
    assert loop["max_rounds"] == 6
    assert "actionable" in loop and "irreducible" in loop


def test_assemble_without_score_has_no_loop_block(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--json",
    ])
    payload = json.loads(res.stdout)
    assert "loop" not in payload


def test_assemble_score_exit_code_tracks_ok_not_verdict(tmp_path):
    # target 100 is unreachable, so verdict is plateau/exhausted, but the exit
    # code must still track validation ok, never the verdict.
    sources, extraction, out = _setup(tmp_path)
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--json", "--score", "--target-score", "100",
    ])
    payload = json.loads(res.stdout)
    assert res.exit_code == (0 if payload["ok"] else 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_assemble.py::test_assemble_score_emits_loop_block -v`
Expected: FAIL — `No such option: --target-score` (or `loop` key missing).

- [ ] **Step 3: Add the four flags to the `assemble` signature**

In `loop_apidoc/cli.py`, in the `assemble` command, insert after the `score_report` option (currently ends at line 219, `)`):

```python
    target_score: Annotated[
        int | None,
        typer.Option("--target-score", min=0, max=100,
                     help="score 自循環目標分(loop verdict 用);省略取 ci profile 預設 85"),
    ] = None,
    prev_score: Annotated[
        int | None,
        typer.Option("--prev-score", min=0, max=100,
                     help="上一輪 score 總分(agent 跨輪帶入,供高原偵測);首輪省略"),
    ] = None,
    round_index: Annotated[
        int,
        typer.Option("--round-index", min=1,
                     help="目前修正輪次(1 起);loop verdict 用"),
    ] = 1,
    max_rounds: Annotated[
        int,
        typer.Option("--max-rounds", min=1,
                     help="修正輪次上限;達上限且未達標→exhausted"),
    ] = 6,
```

- [ ] **Step 4: Compute the loop report after scoring**

In `loop_apidoc/cli.py`, immediately after the `if score_report:` block (after line 264, before `if json_out:`), add:

```python
    loop_payload = None
    if score_payload is not None:
        from loop_apidoc.score import loop_verdict, resolved_min_score

        resolved_target = resolved_min_score(ScoreProfile.CI, target_score)
        loop_payload = loop_verdict(
            prev_score=prev_score,
            curr_score=score_payload.score,
            target=resolved_target,
            round_index=round_index,
            max_rounds=max_rounds,
            findings=score_payload.findings,
        )
```

- [ ] **Step 5: Add the `loop` block to the JSON payload**

In `loop_apidoc/cli.py`, in the `if json_out:` branch, after the `if score_payload is not None: payload["score"] = ...` lines (after line 277), add:

```python
        if loop_payload is not None:
            payload["loop"] = loop_payload.model_dump(mode="json")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_assemble.py -v`
Expected: PASS (existing assemble tests + the 3 new loop tests).

- [ ] **Step 7: Lint**

Run: `uv run ruff check loop_apidoc/score/loop.py loop_apidoc/cli.py`
Expected: no errors (`All checks passed!`).

- [ ] **Step 8: Commit**

```bash
git add loop_apidoc/cli.py tests/test_cli_assemble.py
git commit -m "feat: [score] emit loop block in assemble --score --json"
```

---

### Task 4: Rewire the skill's correction loop onto the verdict

Document the score-gated loop so the agent drives correction off `loop.verdict` when `--score` is used. Docs-only; no code.

**Files:**
- Modify: `skills/loop-apidoc/reference/assemble-and-correction.md`
- Modify: `skills/loop-apidoc/SKILL.md` (steps 5-7, lines ~106-129)

**Interfaces:**
- Consumes: the `loop` block shape and verdict semantics from Task 3.
- Produces: agent-facing prose. No importable symbols.

- [ ] **Step 1: Add the loop-block section to the correction reference**

In `skills/loop-apidoc/reference/assemble-and-correction.md`, after the `## Driving a correction round (max 3 rounds)` section (ends at line 66) and before `## Fail-closed`, insert:

````markdown
## Score-gated loop (`--score`)

Pass `--score --target-score <T> [--prev-score <P>] --round-index <R> --max-rounds <M>`
to make quality — not just "no errors" — the acceptance bar. The `--json` payload then
carries a `loop` block:

```json
{"loop": {"verdict": "continue", "target": 85, "prev_score": 72, "curr_score": 80,
  "round_index": 2, "max_rounds": 6,
  "actionable": [ {"code": "...", "target_file": "...", "field_path": "...",
                   "requery_scope": "...", "score_impact": 12} ],
  "irreducible": [ {"code": "SOURCE_CONFLICT", "evidence": "...", "score_impact": 50} ]}}
```

Drive off `loop.verdict`:

| verdict | meaning | do |
|---|---|---|
| `continue` | below target, improved, rounds left, fixable work remains | for each `loop.actionable`, re-read only `requery_scope` with a read-only subagent, overwrite `target_file`; re-run assemble with `--prev-score <curr_score>` and `--round-index <R+1>` |
| `converged` | `curr_score >= target` | stop — the run met the quality bar |
| `plateau` | below target but no improvement / nothing fixable left | stop — the deficit is irreducible from these sources; present `loop.irreducible` |
| `exhausted` | round cap hit without converging | stop — present `loop.irreducible` and any leftover `loop.actionable` |

**Never** re-read or edit an `irreducible` finding to raise the score — that is the
fail-closed boundary. `curr_score` from this round becomes the next `--prev-score`.
The score and its verdict never change assemble's exit code: a validation `error`
still exits 1 and still needs fixing regardless of verdict.
````

- [ ] **Step 2: Update the "max 3 rounds" note in the same file**

In `skills/loop-apidoc/reference/assemble-and-correction.md`, change the heading on line 56 from:

```markdown
## Driving a correction round (max 3 rounds)
```

to:

```markdown
## Driving a correction round (default max 3 rounds; `--score` uses `--max-rounds`, default 6)
```

- [ ] **Step 3: Add the optional score-gated invocation to SKILL.md step 5**

In `skills/loop-apidoc/SKILL.md`, in `### 5. Assemble + validate`, after the existing fenced `assemble` command (ends line 111), insert:

```markdown
To iterate toward a **quality bar** (not just "no errors"), add the score-gated flags:

```bash
<APIDOC> assemble --sources "<SOURCES>" --extraction "<WORK>" --output "<OUT>" \
  --score --target-score 85 --round-index 1 --max-rounds 6 --json
```

The payload then carries a `loop` block; drive correction off `loop.verdict` (see
`reference/assemble-and-correction.md`). Without `--score`, the loop below is the
baseline validation-gated flow.
```

- [ ] **Step 4: Point SKILL.md step 6 at the verdict when scoring**

In `skills/loop-apidoc/SKILL.md`, replace the `**Max 3 rounds.**` sentence in step 6 (line 128-129, `**Max 3 rounds.** Conflicts / unsupported assertions that survive re-verification → present the gaps to the user; **never fabricate.**`) with:

```markdown
  **Max 3 rounds** for the baseline flow. When you ran with `--score`, drive the
  loop off `loop.verdict` instead (`continue` → correct `loop.actionable` and
  re-assemble with an incremented `--round-index` and `--prev-score`; `converged`
  → done; `plateau`/`exhausted` → stop). Conflicts / unsupported assertions that
  survive re-verification, and anything in `loop.irreducible`, → present the gaps
  to the user; **never fabricate.**
```

- [ ] **Step 5: Verify the docs reference the real contract**

Run: `uv run pytest -q`
Expected: full suite PASS (docs edits don't break code; this is the regression gate before committing the feature).

Run: `grep -n "loop.verdict" skills/loop-apidoc/SKILL.md skills/loop-apidoc/reference/assemble-and-correction.md`
Expected: both files reference `loop.verdict`.

- [ ] **Step 6: Commit**

```bash
git add skills/loop-apidoc/SKILL.md skills/loop-apidoc/reference/assemble-and-correction.md
git commit -m "docs: [score] drive skill correction loop off loop.verdict"
```

---

## Self-Review

**1. Spec coverage:**
- Goal 1 (pure `loop_verdict` + reducible/irreducible split) → Tasks 1-2. ✓
- Goal 2 (`loop` block in `assemble --score --json`) → Task 3. ✓
- Goal 3 (SKILL.md + reference driven by `loop.verdict`) → Task 4. ✓
- Goal 4 (invariant: no auto-fix of irreducible; score never changes validation/exit) → Global Constraints + Task 1 classification + Task 3 `test_assemble_score_exit_code_tracks_ok_not_verdict`. ✓
- Goal 5 (test coverage incl. plateau-terminates) → `test_plateau_when_no_reducible_findings`, `test_plateau_when_score_does_not_improve`, `test_round1_empty_actionable_is_plateau`. ✓
- Contract precedence + verdict values → Task 2 implementation + parametrized tests. ✓
- Product Shape 4 flags → Task 3 Step 3. ✓
- CLI behavior (exit unchanged, flags no-op without `--score`) → Task 3 tests. ✓
- Error handling (input-range guards) → Task 2 `test_out_of_range_inputs_raise`. ✓

Note: the spec's "source-silent-only run terminates at plateau" acceptance criterion is covered at the unit level (`test_plateau_when_no_reducible_findings` uses an all-irreducible finding set). A full assemble-fixture whose only findings are warnings is not added as a separate integration test because the `_setup` fixture's PASS/near-PASS run does not deterministically produce a warning-only finding set across environments; the unit test exercises the exact same code path deterministically.

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". Every code step shows complete code; every command shows expected output. ✓

**3. Type consistency:**
- `classify_findings(list[ScoreFinding]) -> tuple[list, list]` — same name/signature in Task 1 def, Task 2 use, `__init__` export. ✓
- `loop_verdict(*, prev_score, curr_score, target, round_index, max_rounds, findings)` — identical keyword set in Task 2 def, tests, and Task 3 CLI call. ✓
- `LoopReport` fields (`verdict`/`target`/`prev_score`/`curr_score`/`round_index`/`max_rounds`/`actionable`/`irreducible`) — match the JSON keys asserted in Task 3 CLI tests and the reference-doc example. ✓
- `ScoreFinding` fields used (`code`, `severity`, `location`, `evidence`, `suggested_fix`, `category`, `blocking`, `score_impact`) — match `score/models.py`. ✓
- `resolved_min_score(ScoreProfile.CI, target_score)` — matches `score/models.py:84` signature. ✓

---

## Execution Notes

- Run the full suite once at the end: `uv run pytest` then `uv run ruff check .`.
- After Task 4, this branch (`feat/score-improvement-loop`) holds spec + plan + implementation; finish via `superpowers:finishing-a-development-branch` (merge `--no-ff` to `main`, matching repo history).
