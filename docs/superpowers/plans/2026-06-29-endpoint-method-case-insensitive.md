# Endpoint Method Case-Insensitive Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make endpoint method comparison case-insensitive in the plan builder so a stage-05 inventory method written in one case (`get`) and a stage-06 detail or duplicate written in another (`GET`) collapse into one endpoint instead of producing a duplicate.

**Architecture:** A single pure helper `_method_key(method)` returns a normalized (stripped, lower-cased) comparison key. The three places in `loop_apidoc/plan/builder.py` that compare or group endpoints by method — `_dedupe_endpoints` (grouping key) and `_match_index` (two equality checks, path-bearing and path-less/webhook) — compare this key instead of the raw string. The stored `EndpointEntry.method` keeps its source-stated casing (display is unchanged; only matching is normalized). No model change, no generator/validator change — `openapi.py`, `provenance.py`, and `completeness.py` already `.lower()` the method at their output boundaries.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest, `uv` (no `pip`). `builder.py` is pure functions; no new file-I/O.

## Global Constraints

- **Source is the only ground truth.** This fix changes *matching*, never content: no method value is invented or rewritten in the stored plan; `EndpointEntry.method` retains the source's casing. Only comparison keys are normalized.
- **Immutable / pure functions.** `_method_key` is a pure helper; `builder.py` stays free of new side effects.
- **Additive, non-breaking.** `_method_key` is `None`-safe and used only at comparison sites; no public signature changes.
- Python: prefer immutable/pure functions; run `uv run ruff check .` clean before each commit.

---

## File Structure

| File | Responsibility | Change |
| --- | --- | --- |
| `loop_apidoc/plan/builder.py` | Plan assembly: classify, merge stage-06 details, dedupe endpoints | Add `_method_key`; use it in `_dedupe_endpoints` (line ~125) and `_match_index` (lines ~331, ~335). |
| `tests/plan/test_builder.py` | Plan builder unit tests | Add 3 tests: case-insensitive dedupe, case-insensitive path-bearing detail join, case-insensitive path-less webhook detail join. |
| `docs/BENCHMARK_VALIDATION_PLAN.md` | Benchmark plan / known limitations | Remove the now-fixed "method 大小寫敏感" bullet from 「已知忠實限制」. |

---

## Task 1: Case-insensitive endpoint method matching

**Files:**
- Modify: `loop_apidoc/plan/builder.py` (add `_method_key` above `_dedupe_endpoints` at line ~117; edit line ~125, ~331, ~335)
- Modify: `docs/BENCHMARK_VALIDATION_PLAN.md` (the 「已知忠實限制」 bullet)
- Test: `tests/plan/test_builder.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `_method_key(method: str | None) -> str | None` — `None` when method is falsy, else `method.strip().lower()`.

- [ ] **Step 1: Write the failing tests**

Append these three tests to `tests/plan/test_builder.py`. They reuse the file's existing `_manifest()`, `_art()`, `ExtractionResult`, `AnswerArtifact`, `QueryKind` helpers/imports (already at the top of the file — no new imports needed).

```python
def test_endpoints_differing_only_by_method_case_collapse():
    # Stage-05 lists the same operation twice with different method casing
    # (GET vs get). They are the SAME operation and must collapse into one plan
    # endpoint — a case-sensitive dedupe key would leave two.
    block05 = (
        '```json\n{"endpoints": ['
        '{"method":"GET","path":"/u","summary":"upper","source":"api.pdf"},'
        '{"method":"get","path":"/u","summary":"lower","source":"api.pdf"}]}\n```'
    )
    extraction = ExtractionResult(notebook_url="https://nb/x", artifacts=[
        _art("05", QueryKind.INITIAL, block05),
    ])
    plan = build_normalization_plan(extraction, _manifest())
    eps = [e for e in plan.endpoints if e.path == "/u"]
    assert len(eps) == 1


def test_detail_joins_endpoint_despite_method_case_mismatch():
    # Stage-05 endpoint is `post /pay`; the stage-06 detail says `POST /pay`.
    # The detail must join the existing endpoint (not become a second one), so
    # its params/responses merge and exactly one /pay endpoint remains.
    block05 = (
        '```json\n{"endpoints": ['
        '{"method":"post","path":"/pay","summary":"pay","source":"api.pdf"}]}\n```'
    )
    ep0 = ('```json\n{"method":"POST","path":"/pay",'
           '"parameters":[{"name":"amount","in":"body"}],'
           '"responses":[{"status":"200"}],"source":"api.pdf"}\n```')
    extraction = ExtractionResult(notebook_url="https://nb/x", artifacts=[
        _art("05", QueryKind.INITIAL, block05),
        AnswerArtifact(query_id="06-ep0", stage_id="06", kind=QueryKind.INITIAL,
                       answer=ep0, answer_path="answers/06-ep0.txt", returncode=0),
    ])
    plan = build_normalization_plan(extraction, _manifest())
    eps = [e for e in plan.endpoints if e.path == "/pay"]
    assert len(eps) == 1
    assert {p.get("name") for p in eps[0].parameters} == {"amount"}
    assert any(r.get("status") == "200" for r in eps[0].responses)


def test_webhook_detail_joins_despite_method_case_mismatch():
    # Path-less webhook: stage-05 is `POST` (no path); the detail says `post`.
    # The detail must still pair to the webhook endpoint (line ~335 candidate
    # filter), so its responses land on the single hook.
    block05 = (
        '```json\n{"endpoints": ['
        '{"method":"POST","path":null,"summary":"notify","source":"api.pdf"}]}\n```'
    )
    detail = ('```json\n{"method":"post","path":null,'
              '"responses":[{"status":"200","description":"ack"}],'
              '"source":"api.pdf"}\n```')
    extraction = ExtractionResult(notebook_url="https://nb/x", artifacts=[
        _art("05", QueryKind.INITIAL, block05),
        AnswerArtifact(query_id="06-a", stage_id="06", kind=QueryKind.INITIAL,
                       answer=detail, answer_path="answers/06-a.txt", returncode=0),
    ])
    plan = build_normalization_plan(extraction, _manifest())
    hooks = [e for e in plan.endpoints if e.path is None]
    assert len(hooks) == 1
    assert hooks[0].responses == [{"status": "200", "description": "ack"}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/plan/test_builder.py -k "method_case" -v`

Expected: FAIL.
- `test_endpoints_differing_only_by_method_case_collapse` → `assert len(eps) == 1` fails with `2` (case-sensitive dedupe key keeps both).
- `test_detail_joins_endpoint_despite_method_case_mismatch` → `assert len(eps) == 1` fails with `2` (`_match_index` returns None for the case-mismatched detail, so it is appended as a separate endpoint and the case-sensitive dedupe does not merge it).
- `test_webhook_detail_joins_despite_method_case_mismatch` → the detail's responses don't land on the hook (candidate filter `e.method == method` excludes the lowercase detail), so `hooks[0].responses` is `[]` (or a second hook appears) — assertion fails.

- [ ] **Step 3: Add `_method_key` and use it at the three comparison sites**

In `loop_apidoc/plan/builder.py`, insert `_method_key` immediately **above** `_dedupe_endpoints` (currently at line ~117):

```python
def _method_key(method: str | None) -> str | None:
    """Case/space-insensitive comparison key for an HTTP method. Method casing
    is a display detail (sources write GET / get / Get); two endpoints that
    differ only by method case are the SAME operation, so all grouping and
    detail-matching compares this normalized key. The stored
    EndpointEntry.method keeps its source-stated casing."""
    return method.strip().lower() if method else None
```

Then change the grouping key inside `_dedupe_endpoints` — replace this line (~125):

```python
        key = (ep.method, ep.path) if ep.method and ep.path else None
```

with:

```python
        key = (_method_key(ep.method), ep.path) if ep.method and ep.path else None
```

Then in `_match_index`, replace the path-bearing equality check (~331):

```python
            if e.method == method and e.path == path:
```

with:

```python
            if _method_key(e.method) == _method_key(method) and e.path == path:
```

and replace the path-less candidate filter (~335):

```python
        candidates = [idx for idx, e in enumerate(plan.endpoints)
                      if idx not in consumed and e.method == method and e.path is None]
```

with:

```python
        candidates = [idx for idx, e in enumerate(plan.endpoints)
                      if idx not in consumed
                      and _method_key(e.method) == _method_key(method)
                      and e.path is None]
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest tests/plan/test_builder.py -k "method_case" -v`
Expected: PASS (all 3).

- [ ] **Step 5: Run the full builder suite to confirm no regression**

Run: `uv run pytest tests/plan/test_builder.py -v`
Expected: PASS — all pre-existing tests still green (the existing same-case dedupe/merge tests are unaffected because `_method_key` is identity-on-lowercase for already-matching cases).

- [ ] **Step 6: Run the full suite + benchmark harness + lint**

Run:
```bash
uv run pytest
uv run ruff check .
```
Expected: all green, including `tests/test_benchmarks.py` (the committed benchmark `extraction/` fixtures use consistent casing, so behavior is unchanged; this confirms no collateral drift).

- [ ] **Step 7: Update the benchmark plan's known-limitations note**

In `docs/BENCHMARK_VALIDATION_PLAN.md`, the 「已知忠實限制(後續 generator 改進候選)」 section currently lists a single remaining bullet:

```markdown
- pipeline endpoint method 比對大小寫敏感(inventory 小寫 vs endpoint 大寫 → 重複端點;
  觀察未修)。
```

Replace that bullet (the limitation is now fixed) with:

```markdown
- endpoint method 大小寫比對 — ✅ 已修(2026-06-29):`plan.builder._method_key` 以
  正規化 key(strip + lowercase)做端點分組與 stage-06 detail 接合,`GET`/`get` 等
  僅大小寫不同者視為同一操作合併,不再產生重複端點;`EndpointEntry.method` 仍保留來源
  原始大小寫(僅比對正規化,內容不改)。
```

(If, after this fix, no open limitation remains, the section heading may read as a completed item — that is acceptable; do not invent new limitations to fill it.)

- [ ] **Step 8: Commit**

```bash
git add loop_apidoc/plan/builder.py tests/plan/test_builder.py docs/BENCHMARK_VALIDATION_PLAN.md
git commit -m "fix: [plan] case-insensitive endpoint method matching (no duplicate endpoints)"
```

---

## Self-Review

**Spec coverage:** The bug has three comparison sites (dedupe grouping key; path-bearing detail match; path-less webhook candidate filter) — all three are edited in Step 3 and each is covered by a dedicated test in Step 1 (collapse / path-bearing join / webhook join). Display-casing preservation is asserted implicitly (no test rewrites `.method`; the stored value is untouched by `_method_key`). Doc follow-up (Step 7) closes the tracked known-limitation.

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N" — `_method_key` and all three edits are shown verbatim, and all three test bodies are concrete.

**Type consistency:** `_method_key(method: str | None) -> str | None` is used identically at all three sites; both operands are passed through it so `None`/whitespace/case are handled symmetrically. No signature of any existing function changes.
