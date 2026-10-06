# Split loop_apidoc/core/verification.py below the 800-line ceiling

## Goal

`loop_apidoc/core/verification.py` is 1,422 lines. More than 900 of them are
OpenAPI-specific: `_openapi_pointer_derivation` (line 456) and the JSON Pointer and
fragment parsers that follow it (lines 742-1357). Move that code into two new modules
under `loop_apidoc/core/`: one for the derivation dispatch, one for the pointer and
fragment parsers. `verification.py` then keeps only claim verification, comparison, and
relationship construction. Behaviour does not change, and the public import path
`loop_apidoc.core.verification` keeps exporting `verify_claim_support` and
`validate_evidence_bundle`, so no importer changes.

## Out of Scope

- Any behaviour change, renamed function, or changed signature.
- Merging or deduplicating `_ALLOWED_DERIVATIONS` with the derivation names checked
  inside `_openapi_pointer_derivation`.
- Re-exports or compatibility aliases in `verification.py` for names that moved.
- Every other module over 800 lines.
- Tests: no test file is added, removed, or edited.

## Acceptance Criteria

1. `wc -l loop_apidoc/core/verification.py` and each new module under
   `loop_apidoc/core/` report at most 800 lines.
2. Every top-level function, class, and assignment defined in
   `git show 60edca2:loop_apidoc/core/verification.py` is defined exactly once across
   `loop_apidoc/core/verification.py` and the new modules. A Python `ast` script over
   those files shows this, and it is included in the completion report.
3. `uv run python -c "import loop_apidoc.core.openapi_pointers, loop_apidoc.core.openapi_derivation, loop_apidoc.core.verification"`
   exits 0, and neither new module imports `loop_apidoc.core.verification`.
4. `git diff --name-status main...HEAD -- tests/` prints nothing, and
   `uv run pytest tests/core -q` passes.
5. `git grep -n 'from loop_apidoc.core.verification import'` lists the same importers
   and names as at `60edca2`.
6. `git diff --name-status main...HEAD` lists only `M loop_apidoc/core/verification.py`,
   `A loop_apidoc/core/openapi_derivation.py`, `A loop_apidoc/core/openapi_pointers.py`,
   and this Story file (`specs/stories/split-core-verification.md`).
7. `make verify` exits 0.
