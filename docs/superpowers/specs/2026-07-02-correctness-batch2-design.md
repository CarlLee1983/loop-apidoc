# Correctness Batch 2 — Design

**Date:** 2026-07-02
**Status:** Approved for planning
**Predecessor:** correctness batch 1 (merged, commit `586face`). This batch closes the
follow-up items batch 1 deferred plus the three Minor findings from its final review.

## Goal

Close the remaining tracked correctness follow-ups and review minors:

- **Task A** — the one real behaviour fix: reconcile URL path templates with declared
  `in: path` parameters so no path variable is silently undocumented.
- **Task B** (M3) — diff comparison recurses into object-typed parameter schemas.
- **Task C** (Item 7) — fill diff-classification test coverage gaps; fix any real bug a
  new test exposes.
- **Task D** (M1) — remove the duplicated object-detection predicate in the diff
  comparator.
- **Task E** (Item 6 + M2) — defensive CLI summary access; docs ledger updates.

## Non-goals

- No new source formats, no generator feature work beyond path-param reconciliation.
- No change to validation pass/fail semantics other than the new path-param check
  (which is `error`-severity by design — a declared param that cannot be placed is a
  genuine source conflict).
- No refactoring unrelated to the items above.

## Core invariant (unchanged)

The source documents are the only source of truth. Anything a source does not state is
left `null`/recorded, never inferred. The path-param synthesis in Task A is **not** an
exception: a `{token}` in a path template is text the source itself wrote, so naming a
parameter after it is grounding, not inference. Its type stays an empty schema because
the source did not state one.

---

## Task A — Path-parameter reconciliation

### Problem

`generate/openapi.py` builds `in: path` parameters from declared source parameters
(`_build_parameter`, `openapi.py:157`) and unions them per `(path, method)`
(`_build_operation`, `openapi.py:466-491`), but never reconciles them against the
`{token}` variables in the path template. Two mismatches pass silently:

1. **Template token with no declared parameter** — `/users/{id}` where no `id`
   parameter is declared. The path variable is undocumented; consumers do not learn it
   exists, its requiredness, or (absent) its type.
2. **Declared `in: path` parameter with no matching template token** — a source
   declares `id` as `in: path` but the template is `/users`. The parameter cannot be
   placed.

`openapi-spec-validator` (run in `validate/structure.py`) does not strictly enforce
parameter↔template correspondence, so neither case currently surfaces as
`OPENAPI_INVALID`. This is why they are "silent".

### Approach: synthesize + collect

**Generator (`generate/openapi.py`):**
- Extract `{token}` names from each path template (tokens are the substrings inside
  single `{...}` pairs).
- For every token that has no declared `in: path` parameter after the existing union,
  synthesize a minimal parameter:
  `{"name": <token>, "in": "path", "required": true, "schema": {}}`.
  This is grounded in the source path string and follows the existing empty-schema
  convention for unmappable/unstated types (`_build_parameter` already emits `{}`).
- Declared `in: path` parameters are always retained (never dropped), including orphans
  with no matching token — so nothing source-stated disappears before validation.
- Synthesized parameters are ordered deterministically (template-token order) after the
  declared parameters, so output is stable.

**Validator (`validate/consistency.py`, new sub-check called from `check_consistency`):**
- For each path + operation, compute the set of template tokens and the set of declared
  `in: path` parameter names.
- A declared `in: path` parameter whose name is **not** a template token → emit an
  `error`-severity `Issue`, `code = IssueCode.SOURCE_CONFLICT`, with a message naming
  the offending parameter and the path template (e.g. `declared path parameter 'id'
  is absent from path template '/users'`). Deterministic ordering (sorted by path then
  parameter name).
- Synthesized-token coverage needs no issue — synthesis already documents it.

### Boundaries and interfaces

- `check_consistency(openapi: dict, markdown: str) -> list[Issue]` signature is
  unchanged; the new logic is a private helper it calls and whose issues it concatenates.
- The generator change is confined to the operation/paths builders; `_build_parameter`
  is unchanged.

### Testing

New fixtures/tests:
1. Template token, no declaration → generated operation contains the synthesized
   `{name, in: path, required: true, schema: {}}` param; no consistency issue.
2. Declared `in: path` param, no token → exactly one `SOURCE_CONFLICT` error issue
   naming the param and path; run FAILs.
3. Matched token + declared param → param preserved as declared (declared schema wins,
   no duplicate synthesized param); no issue.
4. Multiple tokens (`/a/{x}/b/{y}`) → both synthesized when undeclared; deterministic
   order.

---

## Task B — M3: recurse into object-typed parameter schemas

### Problem

`diff/compare.py` `_compare_parameters` diffs parameter schemas by signature only, so a
property-level change inside an object-typed parameter schema is invisible. Not a
regression (it was equally invisible before batch 1's signature normalization), but a
genuine coverage gap.

### Approach

When a parameter's schema is object-shaped (per the shared `_looks_like_object` helper
from Task D), delegate to the existing `_compare_schema` walk instead of only comparing
signatures, so granular property add/remove/required changes are reported with the same
impact classification used elsewhere.

### Testing

- Object-typed parameter with a property removed → property-level finding at the
  expected location/impact.
- Scalar parameter change → unchanged single signature finding (no regression).

---

## Task C — Item 7: diff-classification coverage

Test-only additions to `tests/diff/`, each asserting the documented classification:

- `info.title` change → CHANGED.
- property-no-longer-required → CHANGED.
- removed component schema → CHANGED.
- callbacks core-field (`verification` / `expected_response`) change → BREAKING.
- validation-issue-removed → SOURCE_ONLY.
- Strengthen `test_response_schema_type_change_is_breaking`: assert the finding
  `location` by **exact equality**, not substring `in`.

If any new test reveals a real misclassification, fix it in `compare.py` under TDD and
note the fix in the task. Otherwise these are pure regression insurance.

---

## Task D — M1: dedup object-detection predicate

`diff/compare.py:82-101` inlines the same object-detection expression in both
`_schema_signature` and `_is_object_schema`. Extract one shared
`_looks_like_object(schema) -> bool` helper that both call, so the "schema changed"
emission and the early-return decision cannot drift. Pure refactor: existing diff tests
(including batch 1's implicit/explicit-object equivalence tests) must stay green with no
behaviour change. Task B consumes this helper.

---

## Task E — Item 6 + M2 cleanup and docs

- **`cli.py:134-137`:** replace literal `report.summary['breaking']` etc. with
  `report.summary.get('breaking', 0)` (matching `diff/report.py:28`). Defensive; the
  keys are currently always present.
- **`docs/PIPELINE_FOLLOWUPS.md`:** add the preprocess flat-destination filename
  collision to the "Open edge" ledger (distinct from the path-parameter edge, which this
  batch resolves); mark items 6 and 7 resolved, mark M1–M3 resolved, and mark the
  path-parameter edge resolved (2026-07-02 correctness batch 2).

---

## Task ordering and dependencies

Task D (shared helper) lands before Task B (which consumes it). Task A, C, and E are
independent. Suggested order: D → B → A → C → E, but the plan may reorder as long as D
precedes B.

## Verification

- `uv run pytest` green (currently 556 passed; batch 2 adds tests).
- `uv run ruff check .` clean.
- New path-param error path proven to FAIL a run (exit code) via CLI/assemble test.
