# Split loop_apidoc/diff/compare.py below the 800-line ceiling

## Goal

`loop_apidoc/diff/compare.py` is 914 lines. About 520 of them access and compare
`openapi.yaml`, from `_collect_operations` (line 52) through `_compare_openapi`
(line 554). The rest compares integration, provenance, validation, manifest, and
preparation artifacts, and assembles the report. Split the file in three:

- `loop_apidoc/diff/findings.py` holds the finding primitives: `_METHODS`,
  `_IMPACT_ORDER`, `_SUMMARY_KEYS`, `_finding`, `_sorted_findings`, and `_summary`. It
  is the lowest layer, so the other two modules do not import each other in a cycle.
- `loop_apidoc/diff/openapi_compare.py` holds the OpenAPI access and comparison code.
- `loop_apidoc/diff/compare.py` keeps the other artifact comparisons and
  `build_diff_report`.

Behaviour does not change. `build_diff_report` stays at its current import path.

## Out of Scope

- Any behaviour change, renamed function, or changed signature.
- Re-exports or compatibility aliases in `compare.py` for names that moved.
- `loop_apidoc/diff/__init__.py`, `loader.py`, `models.py`, and `report.py`.
- Every other module over 800 lines.
- Test changes other than the one import line in criterion 4.

## Acceptance Criteria

1. `wc -l` reports at most 800 lines for each of `loop_apidoc/diff/compare.py`,
   `loop_apidoc/diff/findings.py`, and `loop_apidoc/diff/openapi_compare.py`.
2. Every top-level function, class, and assignment defined in
   `git show 60edca2:loop_apidoc/diff/compare.py` is defined exactly once across the
   three modules. A Python `ast` script over those files shows this, and it is
   included in the completion report.
3. `loop_apidoc/diff/findings.py` imports neither `loop_apidoc.diff.compare` nor
   `loop_apidoc.diff.openapi_compare`, and `loop_apidoc/diff/openapi_compare.py` does
   not import `loop_apidoc.diff.compare`.
4. `git diff main...HEAD -- tests/` changes only the import line in
   `tests/diff/test_compare_openapi.py`, which now imports `_looks_like_object` from
   `loop_apidoc.diff.openapi_compare`. `uv run pytest tests/diff tests/review -q`
   passes.
5. The `loop_apidoc/diff/` row of the package table in `docs/ARCHITECTURE.md`
   (`### 套件職責表`) names `findings.py` and `openapi_compare.py` with their
   responsibilities, and the rest of `docs/ARCHITECTURE.md` is unchanged.
6. `git diff --name-status main...HEAD` lists only `M loop_apidoc/diff/compare.py`,
   `A loop_apidoc/diff/findings.py`, `A loop_apidoc/diff/openapi_compare.py`,
   `M tests/diff/test_compare_openapi.py`, `M docs/ARCHITECTURE.md`, and this Story
   file (`specs/stories/split-diff-compare.md`).
7. `make verify` exits 0.
