# Make the stripe-basic-rest extraction state only what spec3.sdk.json states

## Goal

The committed extraction for `stripe-basic-rest` is hand-normalized, so some of its
values are not what the supplier source says. This breaks the project's core invariant:
a value the source does not state stays `null` and is recorded in `missing`. Legacy
validation passes the case anyway. The Core shadow replay rejects it, which is how the
stripe parity attempt found the problem.

The reference source is the snapshot at
`https://raw.githubusercontent.com/stripe/openapi/3881db83dff8d170d4b7ef7e00e1801cd617e891/openapi/spec3.sdk.json`,
SHA-256 `a58d0f7ce76116839b2031fe1fff178283f5c686c6cdbdeaf324d6670a97fe9e`. An audit
against it found:

| Class | Count | Example (extraction → source) |
| --- | --- | --- |
| Truncated or whitespace-collapsed descriptions | 28 body params, 5 schema fields | `amount` cut mid-sentence |
| Rewritten descriptions | 17 body params, 3 schema fields | newline paragraphs merged, wording changed |
| Response description | 6 | `Returns the PaymentIntent object.` → `Successful response.` |
| Response `schema_ref` and schema name | 6 + 1 | `PaymentIntent` → `payment_intent` |
| Single type chosen from an `anyOf` | 18 body params, 4 schema fields | `customer: string` → `anyOf`, no single type |
| Security scheme `details` | 2 | paraphrase → the scheme's own `description` |
| Environment name | 1 | `Production` → no name in `servers` |
| Request `description` | 5 | `Form-urlencoded body. …` → requestBody has no description |
| `operational` prose | 3 | e.g. `sk_...`, bracket syntax, error object, none of which the spec states |

Correct the extraction so every value is either the source's verbatim value or `null`
with a `missing` entry. The subset keeps the same operations, parameters, and schema
fields, and the benchmark keeps passing.

## Out of Scope

- Adding `evidence[]`, changing `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`, or any parity
  work. That stays in `specs/stories/stripe-exact-evidence-parity.md`.
- Representation questions that are not value errors: security listed as scheme names,
  security scheme `name` as the scheme key, and inline request bodies. Those belong to
  the separate Core derivation Story.
- Adding or removing operations, parameters, or schema fields. The subset's scope
  stays as documented in `notes.md`.
- Any change under `loop_apidoc/` or `scripts/`. Under `tests/`, the only allowed change
  is in `tests/test_benchmarks.py`, where the stripe fixture's schema name
  `PaymentIntent` becomes `payment_intent`. That is amended by the owner because the
  diff test's synthetic endpoint hardcodes the old name; no test logic changes.
- The legacy no-speculation gap that let these values pass. It is tracked separately as
  a GitHub issue.
- `benchmarks/stripe-basic-rest/expected/minimum.json` and `core-parity.json`.

## Acceptance Criteria

1. An audit script compares every extracted value against `spec3.sdk.json` at the
   SHA-256 above, after `snapshot-openapi-url` retrieves it into the gitignored
   `sources/`. The script covers descriptions, types, required flags, response
   status/description/`schema_ref`, schema names, security scheme details,
   environment names, and request descriptions. It reports zero mismatches; a value is
   either byte-identical to the source value at the cited location, or `null`. The
   script lives outside the repository, and its output is in the completion report.
2. Every value set to `null` by this change has a corresponding entry in the
   enclosing `missing` list that states what the source does not provide, for example
   "`customer` is `anyOf` [string, customer]; no single type is stated".
3. Each `operational` entry either quotes only what the source states at its cited
   location or is removed. No entry states anything absent from `spec3.sdk.json`.
4. The set of operations, the parameter names per operation, and the schema field
   names are unchanged. A script compares them between `main` and `HEAD`, and its
   output is in the completion report.
5. `uv run loop-apidoc verify-extraction --sources benchmarks/stripe-basic-rest/sources --extraction benchmarks/stripe-basic-rest/extraction`
   exits 0.
6. `uv run pytest tests/test_benchmarks.py -k stripe -rs` reports no failures. Its
   skips, if any, are listed with their reasons in the completion report.
7. `git diff --name-status main...HEAD -- benchmarks/stripe-basic-rest/expected/`
   prints nothing, or changes only `validation.expect.json`. Every changed expectation
   in that file must be caused directly by a value this Story set to `null`, and each
   one is named in the completion report.
8. `benchmarks/stripe-basic-rest/notes.md` records the correction and the source
   SHA-256 it was checked against.
9. `git ls-files benchmarks/stripe-basic-rest/sources benchmarks/stripe-basic-rest/source-quality`
   prints nothing.
10. `git diff --name-status main...HEAD` lists only files under
    `benchmarks/stripe-basic-rest/extraction/`, `benchmarks/stripe-basic-rest/notes.md`,
    optionally `benchmarks/stripe-basic-rest/expected/validation.expect.json`,
    `tests/test_benchmarks.py` (only `PaymentIntent` → `payment_intent`), and this
    Story file (`specs/stories/stripe-extraction-source-verbatim.md`).
11. `make verify` exits 0.
