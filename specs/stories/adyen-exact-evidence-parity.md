# Bring adyen-payments-multimethod to claim-complete exact-evidence parity

## Goal

ADR 0016 makes Core graduation wait for exact-evidence parity on every restored
source-backed benchmark. `adyen-payments-multimethod` cites one OpenAPI document,
`sources/CheckoutService-v71.json` (gitignored, SHA-256
`9e426ae2bf007b148c393c5f163bbb0abe54959172b4d85676aedbd178b2b0b0`, restored as
recorded in the case's `notes.md`). Its replay today is legacy `passed` / Core `accept`
with 29 Core claims, all unverified.

Bind every material claim in the committed extraction to v1 `evidence[]` with exact
`json_pointer` locators into that document. Then add the case to the exact-evidence
parity lane, so `test_case_obeys_declared_core_parity_contract` replays it.

Core compares each JSON Pointer's value with the claim value, unless an allowed
Structural Derivation applies (`CONTEXT.md`). Two derivations this case needs are
prerequisites, each in its own Story, and both must be merged before this Story starts:

- `core-error-code-derivation`, for the 5 error `/code` claims;
- `core-test-case-example-operation-derivation`, for the 2 test cases' operation
  references.

The extraction states some values the source does not. Correct them as follows, and
change nothing else:

- The `description` of each operation response becomes that response's `description`
  string in the source.
- The `meaning` of each of the 5 `errors` becomes the `description` string of the
  `/payments` response it cites.
- The `name` of each of the 2 `test_cases` becomes the `summary` string of the
  `components.examples` entry it cites.
- The environment `name` (`test`) is removed. The source names no environment.
- The 4 `field_conditions` are removed. The source states them only through the
  `paymentMethod` `oneOf` and each detail schema's `required` list, which the schema
  claims already carry. `notes.md` records what they said.
- The 2 `operational` entries are removed. Their text is the extraction's own
  explanation, not source text.

## Out of Scope

- Any change under `loop_apidoc/`. If a claim cannot be supported with the pipeline
  after the two prerequisite Stories, stop and report it.
- Any source other than the document above. On a SHA-256 mismatch, stop.
- Committing anything under `sources/`, `source-quality/`, or `work/`.
- Changing extracted values other than the corrections listed in the Goal, and
  renaming any schema, security scheme, or example key.
- Moving the removed facts into `missing`. The source states them; they are not gaps.
- `expected/core-parity.json`, and the other cases without parity.
- ADR 0016 and the CI workflow.

## Acceptance Criteria

1. `shasum -a 256 benchmarks/adyen-payments-multimethod/sources/CheckoutService-v71.json`
   reports `9e426ae2bf007b148c393c5f163bbb0abe54959172b4d85676aedbd178b2b0b0`. The
   completion report shows the command and its output.
2. `uv run loop-apidoc verify-extraction --sources benchmarks/adyen-payments-multimethod/sources --extraction benchmarks/adyen-payments-multimethod/extraction`
   exits 0.
3. Every `evidence` entry under `benchmarks/adyen-payments-multimethod/extraction/` has
   source `CheckoutService-v71.json` and a `json_pointer` locator. A script outside the
   repository counts the entries and the exceptions, and the exception count is 0. The
   script and its output are in the completion report.
4. `"adyen-payments-multimethod"` is a member of `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`
   in `scripts/quality_gate.py`.
5. `uv run pytest tests/test_benchmarks.py -k "adyen" -rA` reports no failures and no
   skips, and lists
   `test_case_obeys_declared_core_parity_contract[adyen-payments-multimethod]` as passed.
6. A script loads each file under `benchmarks/adyen-payments-multimethod/extraction/` on
   both sides of `main...HEAD`, deletes every `evidence` key, and prints the remaining
   differences. Each one is a correction or removal listed in the Goal. Its output is in
   the completion report.
7. `git diff main...HEAD -- benchmarks/adyen-payments-multimethod/expected/minimum.json`
   changes only `counts.field_conditions`, from `4` to `0`, recorded with
   `scripts/benchmark_counts.py --record`.
8. `git diff --name-status main...HEAD -- benchmarks/adyen-payments-multimethod/expected/validation.expect.json`
   prints nothing, or its diff changes only `current_issue_classes` counts and their
   explanatory text and names each warning that was added or removed.
9. `benchmarks/adyen-payments-multimethod/notes.md` records the parity result, the
   corrections, and the removed field conditions and operational entries.
   `docs/PRODUCT_EXTENSION_ROADMAP.md` and `docs/BENCHMARK_VALIDATION_PLAN.md` name
   Adyen as a parity case. Every parity count they state equals the number of members of
   `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`.
10. `git ls-files benchmarks/adyen-payments-multimethod/sources benchmarks/adyen-payments-multimethod/source-quality benchmarks/adyen-payments-multimethod/work`
    prints nothing.
11. `git diff --name-status main...HEAD` lists only files under
    `benchmarks/adyen-payments-multimethod/extraction/`,
    `benchmarks/adyen-payments-multimethod/notes.md`,
    `benchmarks/adyen-payments-multimethod/expected/minimum.json`,
    `benchmarks/adyen-payments-multimethod/expected/validation.expect.json`,
    `scripts/quality_gate.py`, `tests/test_quality_gate.py`,
    `docs/PRODUCT_EXTENSION_ROADMAP.md`, `docs/BENCHMARK_VALIDATION_PLAN.md`, and this
    Story file (`specs/stories/adyen-exact-evidence-parity.md`).
12. `make verify` exits 0.
