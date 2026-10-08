# Name each benchmark request body's schema in `request.schema_ref`

## Goal

An endpoint's `request.schema_ref` names the inventory schema of its request body,
as `responses[].schema_ref` does for a response. The claim projection reads it to give
an operation its `request_schema_ref` (`loop_apidoc/plan/claim_projection.py`), and the
cross-file gate checks that it names an inventory schema
(`loop_apidoc/agentcli/cross_file.py`). `request.schema` is a prose or type
description.

Four committed benchmarks write the schema name only in `request.schema`, so Core sees
no request schema and the gate checks none:

| Case | Requests | Sources restored |
| --- | --- | --- |
| `ecpay-creditcard-pdf` | 5 | yes, in the exact-evidence parity lane |
| `tappay-backend` | 5 | no |
| `newebpay-mpg` | 3 | no |
| `line-pay-online-v3` | 1 | no |

For each request whose `schema` string equals an `inventory.schemas[].name` of the same
case and whose `schema_ref` is `null` or absent, set `schema_ref` to that string. Leave
`schema` unchanged: the generator still reads it, and the generated OpenAPI must not
change in this Story.

`ecpay-creditcard-pdf` is in the parity lane, so each new operation claim
`/request_schema_ref` needs evidence. The path-less webhook endpoint
(`PaymentResultNotification`) projects to a webhook claim, which carries no request
schema, so 4 operations gain the claim. Bind each one under the range rule of
`specs/stories/ecpay-exact-evidence-parity.md`, with `/request_schema_ref` added to the
identifiers of clause 4: its evidence reuses a range that the same endpoint cites for a
path held to clause 2 or 3.

A later Story adds a gate rule that rejects a schema name written only in `schema`.
This Story makes the committed benchmarks satisfy that rule first.

## Out of Scope

- Any change under `loop_apidoc/`, and the gate rule itself.
- Changing or removing `request.schema`, or any value other than the added
  `schema_ref` and the ecpay evidence for it.
- A `request.schema` that is prose and names no inventory schema, such as the other 3
  requests of `newebpay-mpg`.
- Generating a `$ref` for a request body.
- Restoring the sources of `tappay-backend`, `newebpay-mpg`, or `line-pay-online-v3`.
- Committing anything under `sources/`, `source-quality/`, or `work/`.
- `expected/core-parity.json`, ADR 0016, and the CI workflow.

## Acceptance Criteria

1. A script outside the repository reads every `benchmarks/*/extraction/`. For each
   request and response whose `schema` string equals an inventory schema name of its
   case, it checks that `schema_ref` equals `schema`. It prints the number of such
   requests per case, which is 5 for `ecpay-creditcard-pdf`, 5 for `tappay-backend`, 3
   for `newebpay-mpg`, and 1 for `line-pay-online-v3`, and a violation count of 0. The
   script and its output are in the completion report.
2. A script loads each file under the four cases' `extraction/` on both sides of
   `main...HEAD`, deletes every `evidence` key, and prints the remaining differences.
   Each one is an added `request.schema_ref` equal to that request's `schema`, 14 in
   all. Its output is in the completion report.
3. A script outside the repository calls `cross_file_violations` from
   `loop_apidoc/agentcli/cross_file.py` on each of the four cases' committed
   extraction and prints 0 violations per case. The script and its output are in the
   completion report.
4. Each of the 4 `ecpay-creditcard-pdf` operations with a path has evidence for
   `/request_schema_ref`. A script outside the repository applies the range rule, with
   `/request_schema_ref` in clause 4, to every `evidence` entry under
   `benchmarks/ecpay-creditcard-pdf/extraction/` and prints the number of entries it
   checked and a violation count of 0. The script and its output are in the completion
   report.
5. `uv run loop-apidoc verify-extraction --sources benchmarks/ecpay-creditcard-pdf/sources --extraction benchmarks/ecpay-creditcard-pdf/extraction`
   exits 0.
6. `uv run pytest tests/test_benchmarks.py -k "ecpay" -rA` reports no failures and no
   skips, and lists
   `test_case_obeys_declared_core_parity_contract[ecpay-creditcard-pdf]` as passed.
7. `git diff main...HEAD -- benchmarks/ecpay-creditcard-pdf/expected/` prints nothing,
   or changes only counts recorded with `scripts/benchmark_counts.py --record` and
   `current_issue_classes` counts with explanatory text that names each warning added
   or removed. `git diff main...HEAD -- benchmarks/tappay-backend/expected/ benchmarks/newebpay-mpg/expected/ benchmarks/line-pay-online-v3/expected/`
   prints nothing.
8. The `notes.md` of each of the four cases records the added `schema_ref`, and why.
9. `git ls-files benchmarks/ecpay-creditcard-pdf/sources benchmarks/ecpay-creditcard-pdf/source-quality benchmarks/ecpay-creditcard-pdf/work`
   prints nothing.
10. `git diff --name-status main...HEAD` lists only files under the four cases'
    `extraction/` and `expected/`, their `notes.md`, and this Story file
    (`specs/stories/benchmark-request-schema-ref.md`).
11. `make verify` exits 0.
