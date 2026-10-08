# Derive a test case's operation reference from an OpenAPI request example

## Goal

Core represents a test case as an `integration_mechanic` claim whose operation
reference is the claim path `/operation_refs/<operation identity>`
(`loop_apidoc/domain/claim_paths.py`, integration-mechanic paths). Since #187, a
test case's `paths.{path}.{method}` reference projects to that canonical identity.

An OpenAPI document ties an example to its operation by where it sits. The example
entry `/paths/~1payments/post/requestBody/content/application~1json/examples/card-direct`
holds `{"$ref": "#/components/examples/post-payments-card-direct"}`. The operation
identity is not a value at any pointer. `_openapi_pointer_derivation_name` in
`loop_apidoc/shadow/bridge.py` returns no derivation for an `integration_mechanic`
claim, so Core compares the identity string with the example entry object and reports
`EVIDENCE_VALUE_MISMATCH`.

`adyen-payments-multimethod` has 2 test cases (`card-direct`, `ideal`), each tied to
`POST /payments` this way. Their operation references cannot be supported today. This
is the second of two Core gaps that block adyen exact-evidence parity.

Add one version-1 derivation, failing closed:

- `openapi_operation_ref_from_request_example_pointer`: the evidence is
  `/paths/<p>/<m>/requestBody/content/<media>/examples/<key>`, and the fragment value is
  an object. It proves the `integration_mechanic` claim path
  `/operation_refs/<identity>`, where `<identity>` is the canonical operation identity
  of `<m>` and `<p>`.

## Out of Scope

- Response examples, parameter examples, the singular `example` field, and
  `/components/examples/<key>` pointers. Each one is refused, never supported.
- Checking that the test case's `/name` evidence and its operation-reference evidence
  name the same example. `/name` is supported by binding the example's `summary` string.
- Operation references of `transport_policy`, `idempotency_rule`,
  `line_currency_policy`, `amount_direction`, and `error` claims.
- Changing the existing derivations, the claim projection, or Core's claim model.
- Adding `evidence[]` to any committed benchmark, or changing
  `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`.

## Acceptance Criteria

1. TDD comes first. A new test in `tests/core/test_verification.py` fails before the
   change, and the completion report shows that red run. After the change it passes,
   with relationship `DERIVED_SUPPORT` and reason `OPENAPI_POINTER_DERIVATION_MATCH`,
   for the claim path `/operation_refs/operation:POST:~1payments` proven by
   `/paths/~1payments/post/requestBody/content/application~1json/examples/card-direct`.
2. Each of these is refused and never produces support. Each case has a test, and the
   completion report states the reason code for each:
   1. the pointer addresses a response example,
      `/paths/~1payments/post/responses/200/content/application~1json/examples/<key>`;
   2. the pointer is `/components/examples/<key>`;
   3. the pointer addresses the singular `example`, or has segments beyond `<key>`;
   4. the pointer's operation is `POST /payments/details` but the claim path names
      `operation:POST:/payments`;
   5. the fragment value is not an object;
   6. the claim kind is not `integration_mechanic`, for example a `transport_policy`
      claim at `/operation_refs/<identity>`.
3. The derivation name, version `"1"`, is added to `_ALLOWED_DERIVATIONS`
   (`loop_apidoc/core/verification.py`) and to the dispatch in
   `loop_apidoc/core/openapi_derivation.py`. `_openapi_pointer_derivation_name` in
   `loop_apidoc/shadow/bridge.py` selects it only for claim kind `integration_mechanic`,
   an `/operation_refs/<identity>` claim path, and a request-example pointer, and a test
   in `tests/shadow/test_bridge_claims.py` covers that selection. Existing selections
   stay unchanged.
4. Existing tests pass unchanged: `git diff main...HEAD -- tests/` adds tests only and
   edits no existing assertion.
5. A reproduction outside the repository uses the adyen snapshot
   (`benchmarks/adyen-payments-multimethod/sources/CheckoutService-v71.json`, SHA-256
   `9e426ae2bf007b148c393c5f163bbb0abe54959172b4d85676aedbd178b2b0b0`). It binds the
   operation-reference evidence of the 2 test cases in a scratch copy of the extraction
   to their request-example pointers (`examples/card-direct`, `examples/ideal`) and runs
   the shadow pipeline. Both bindings are `derived_support`. The script and its output
   are in the completion report.
6. `wc -l` reports at most 800 lines for `loop_apidoc/core/openapi_pointers.py`,
   `loop_apidoc/core/openapi_derivation.py`, and `loop_apidoc/core/verification.py`. If
   a module would exceed 800, stop and report rather than split it inside this Story.
7. `git diff --name-status main...HEAD` lists only those three Core modules,
   `loop_apidoc/shadow/bridge.py`, test files under `tests/core/` or `tests/shadow/`, and
   this Story file (`specs/stories/core-test-case-example-operation-derivation.md`).
8. `make verify` exits 0.
