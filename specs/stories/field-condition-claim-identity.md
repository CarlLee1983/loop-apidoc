# Give each field condition its own claim identity

## Goal

`iter_plan_claim_projections` in `loop_apidoc/plan/claim_projection.py` projects every
`integration.field_conditions` entry to an `integration_mechanic` claim. `_subject`
(line 123) names a `FieldCondition` by its `scope` alone, so one scope with several
conditions yields several proposals with the same canonical identity.
`reconcile_claims` in `loop_apidoc/core/reconciliation.py` groups proposals by that
identity. When each proposal is fully supported and their values differ, the group
becomes one `conflicting` claim.

Two benchmarks have several conditions on one scope: `ecpay-creditcard-pdf` (three on
`AioCheckOutRequest`) and `adyen-payments-multimethod` (four on
`paths./payments.post body`). A scratch probe gave every ecpay `field_conditions`
entry its own whole-file `line_range` evidence and ran the shadow pipeline. Core
reported `claim:integration_mechanic:AioCheckOutRequest:definition` as `conflicting`,
with values `BindingCard=1`, `ChoosePayment 為銀聯卡或非即時付款`, and `使用信用卡分期`,
and returned the verdict `reject`. Each condition is a separate source fact, not a
competing value for one fact.

When a `FieldCondition` has a non-blank `when`, name it `<scope> when <when>`. With a
blank or missing `when`, keep naming it by `scope` alone, or by its plan location when
`scope` is missing too.

## Out of Scope

- The claim value (`_condition_value`) and the material claim paths of
  `integration_mechanic`.
- The subjects of every other claim kind, including `ContractTestCase` and `CryptoScheme`.
- Making identity construction tolerate an ASCII colon in `scope` or `when`.
  `canonical_claim_identity` rejects colons for every subject today.
- Adding `evidence[]` to any benchmark, or changing `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`.
- `reconcile_claims` and its grouping rule.

## Acceptance Criteria

1. TDD, so the failing test comes first. A new test passes a plan to
   `iter_plan_claim_projections` with two `FieldCondition` entries that have the same
   `scope` and different `when`. It asserts that their subjects are distinct and equal
   `<scope> when <when>`. The completion report shows the test failing before the
   change and passing after it.
2. A test asserts that a `FieldCondition` with `when` unset keeps `scope` as its
   subject.
3. A test runs `build_runtime_result` and `reconcile_claims` (or `execute_shadow`) on a
   plan whose two same-scope conditions both carry supporting evidence. It asserts
   that they produce two `supported` claims and no `conflicting` claim.
4. Existing tests pass unchanged: `git diff main...HEAD -- tests/` only adds tests or
   adds cases to existing test files, with no edited assertions.
5. A reproduction outside the repository repeats the ecpay probe above: the restored
   `gw_p110.pdf.md` with SHA-256
   `d42d3337d15d4c91ffad0e8efa48b294e9e1404149f20ae73b70b040cbe650b4`, every
   `field_conditions` entry bound in a scratch copy of the extraction. Core reports
   none of the `AioCheckOutRequest` conditions as `conflicting`. The script and its
   output are in the completion report.
6. `git diff --name-status main...HEAD` lists only
   `loop_apidoc/plan/claim_projection.py`, test files under `tests/`, and this Story
   file (`specs/stories/field-condition-claim-identity.md`).
7. `make verify` exits 0.
