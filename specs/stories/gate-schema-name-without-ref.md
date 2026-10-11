# Reject a schema name written only in `schema`

## Goal

`request.schema_ref` and `responses[].schema_ref` name an inventory schema; `schema` is a
prose or type description. The claim projection
(`loop_apidoc/plan/claim_projection.py`) and the cross-file gate
(`loop_apidoc/agentcli/cross_file.py`) read only `schema_ref`. An extraction that
writes the schema name only in `schema` therefore loses the link silently: Core sees no
request schema, and the gate checks none. Fourteen committed requests did this until
the `benchmark-request-schema-ref` Story, which is a prerequisite and must be merged
before this Story starts.

The extraction contract (`skills/loop-apidoc/reference/extraction-schemas.md`) lists no
`schema_ref` in `request`. Add it, and state what each key holds.

Add one cross-file invariant, failing closed. For the `request` and each of the
`responses` of an endpoint: when `schema` is a string equal to an
`inventory.schemas[].name` and `schema_ref` is `null` or absent, report a violation.
The message names the endpoint, the field (`request.schema` or
`responses[<idx>].schema`), and the value, and tells the author to set `schema_ref`.
`check_extraction` already folds in every cross-file violation, so `assemble` and
`verify-extraction` both reject it.

## Out of Scope

- A `schema_ref` that differs from a `schema` naming another schema. Only the missing
  `schema_ref` is checked.
- A `schema` that names no inventory schema, including prose that contains a schema
  name.
- Generating a `$ref` for a request body, and any other generator change.
- Changing the claim projection, Core, or any committed benchmark.
- `docs/` other than `docs/ARCHITECTURE.md`.

## Acceptance Criteria

1. TDD comes first. A new test in `tests/agentcli/test_cross_file.py` fails before the
   change, and the completion report shows that red run. After the change it passes:
   an endpoint whose `request.schema` is `"PayRequest"`, an inventory schema name, with
   `schema_ref` `null` yields exactly one violation, and its message contains
   `request.schema` and `'PayRequest'`.
2. A test covers the same case for `responses[0]`, whose message contains
   `responses[0].schema`.
3. Each of these yields no violation from the new invariant, and each has a test:
   1. `schema` and `schema_ref` both equal the schema name;
   2. `schema` is prose that is not a schema name;
   3. `schema` is `null`;
   4. `request` is `null`.
4. Existing tests pass unchanged: `git diff main...HEAD -- tests/` adds tests only and
   edits no existing assertion.
5. In `skills/loop-apidoc/reference/extraction-schemas.md`, the endpoint `request`
   object lists `"schema_ref":"str|null"`, and the text states that `schema_ref` names
   an `inventory.schemas[].name` and `schema` is a prose or type description, and that
   a schema name written only in `schema` is rejected.
6. `docs/ARCHITECTURE.md` names the new invariant where it lists the cross-file
   invariants, in both the Chinese and the English description of `cross_file.py`, and
   the invariant count it states matches.
7. A script outside the repository calls `cross_file_violations` on every committed
   `benchmarks/*/extraction/` and prints 0 violations. The script and its output are in
   the completion report.
8. `wc -l loop_apidoc/agentcli/cross_file.py` reports at most 800 lines.
9. `git diff --name-status main...HEAD` lists only `loop_apidoc/agentcli/cross_file.py`,
   `tests/agentcli/test_cross_file.py`,
   `skills/loop-apidoc/reference/extraction-schemas.md`, `docs/ARCHITECTURE.md`, and
   this Story file (`specs/stories/gate-schema-name-without-ref.md`).
10. `make verify` exits 0.
