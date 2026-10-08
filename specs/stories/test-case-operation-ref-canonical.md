# Resolve a test case's documented `paths.{path}.{method}` operation reference in Core

## Goal

The extraction contract states a test case's `operation_ref` as
`paths.{path}.{method}` (`skills/loop-apidoc/reference/extraction-schemas.md`, the
`test_cases` shape). The legacy validator resolves that form
(`loop_apidoc/validate/integration.py`, the `contract.test_cases` loop).

Core does not resolve it. `_test_case_value` in `loop_apidoc/plan/claim_projection.py`
passes the reference through `_canonical_operation_reference`, which only rewrites
`METHOD /path` to a canonical `operation:` identity. A `paths./Cashier/AioCheckOut/V5.post`
reference stays as it is. When the test case claim is supported, Core's
`INTEGRATION_REFERENCE_UNRESOLVED` rule (`loop_apidoc/domain/rules.py`) cannot find it
among the operation identities and rejects the contract.

This came up during the ecpay exact-evidence parity work. With every ecpay claim
supported (commit `cdf226d` on `bench/ecpay-exact-evidence-parity`), Core reports
`INTEGRATION_REFERENCE_UNRESOLVED` for `paths./Cashier/AioCheckOut/V5.post` and returns
`reject`. `adyen-payments-multimethod` uses the same form (`paths./payments.post`).

Make `_canonical_operation_reference` also rewrite `paths.{path}.{method}` to the
canonical identity of that method and path. Split it the way the legacy validator
does: the method is the text after the last `.`, and the path is everything between
`paths.` and that `.`.

## Out of Scope

- Changing the extraction contract text or the legacy validator.
- Any benchmark file, including the ecpay and adyen extractions.
- Other reference forms, and the claim value or material paths of
  `integration_mechanic`.
- `loop_apidoc/domain/rules.py`.

## Acceptance Criteria

1. TDD, so the failing test comes first. A new test projects a `ContractTestCase` with
   `operation_ref="paths./Cashier/AioCheckOut/V5.post"` through
   `iter_plan_claim_projections`. It asserts that the value's `operation_refs` equals
   `[canonical_operation_identity("POST", "/Cashier/AioCheckOut/V5")]`. The completion
   report shows the test failing before the change and passing after it.
2. A test asserts that a reference whose path contains a dot,
   `paths./list.json.get`, resolves to the identity of `GET /list.json`.
3. A test asserts that the `METHOD /path` form and an existing `operation:` identity
   still project as before.
4. A test runs `execute_shadow` on a plan with one supported endpoint and one supported
   test case that references it as `paths.{path}.{method}`. It asserts that the
   decision has no `INTEGRATION_REFERENCE_UNRESOLVED` finding.
5. Existing tests pass unchanged: `git diff main...HEAD -- tests/` only adds tests or
   adds cases to existing test files, with no edited assertions.
6. A reproduction outside the repository copies the ecpay extraction at commit
   `cdf226d`, with the restored `gw_p110.pdf.md` (SHA-256
   `d42d3337d15d4c91ffad0e8efa48b294e9e1404149f20ae73b70b040cbe650b4`). It re-binds
   only the test case's `/operation_refs/…` evidence entry to the claim path the new
   projection produces (`/operation_refs/operation:POST:~1Cashier~1AioCheckOut~1V5`),
   then runs the shadow pipeline. It reports no `INTEGRATION_REFERENCE_UNRESOLVED`
   finding. The script and its output are in the completion report.
7. `git diff --name-status main...HEAD` lists only
   `loop_apidoc/plan/claim_projection.py`, test files under `tests/`, and this Story
   file (`specs/stories/test-case-operation-ref-canonical.md`).
8. `make verify` exits 0.
