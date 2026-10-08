# Derive an error code claim from its OpenAPI response key

## Goal

Core represents a documented error by an `error` claim whose `/code` is the error code
(`loop_apidoc/domain/claim_paths.py`, error paths). An OpenAPI document states an HTTP
error as a response key: the `400` in `/paths/~1payments/post/responses/400`. The key is
not a value at any pointer. `_openapi_pointer_derivation_name` in
`loop_apidoc/shadow/bridge.py` returns no derivation for an `error` claim, so the bridge
proposes `STRUCTURED_FIELD_PATH`. Core then compares the claim value `"400"` with the
whole response object and reports `EVIDENCE_VALUE_MISMATCH`.

`adyen-payments-multimethod` has 5 error claims (`400`, `401`, `403`, `422`, `500`),
each cited to a `/payments` response. They cannot be supported today. This is one of
two Core gaps that block adyen exact-evidence parity.

Add one version-1 derivation, failing closed:

- `openapi_error_code_from_response_pointer`: the evidence is
  `/paths/<p>/<m>/responses/<status>`, and it proves the `error` claim `/code` =
  `<status>`. `<status>` must be a three-digit numeric key whose first digit is `4` or
  `5`. It reuses the canonical response-pointer parsing of
  `openapi_response_status_from_pointer`.

## Out of Scope

- `2xx`, `1xx`, `3xx`, `default`, and range keys such as `4XX`. Each one is refused,
  never supported.
- The error claim's `/description` and `/applicable_to/<op>` paths. A description is
  supported by binding the response's `description` string. `applicable_to` is not
  derived from the pointer's operation.
- Error codes stated anywhere other than an OpenAPI response key, such as in a body
  field or a prose table.
- Changing the existing derivations, or Core's claim model for errors.
- Adding `evidence[]` to any committed benchmark, or changing
  `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`.

## Acceptance Criteria

1. TDD comes first. A new test in `tests/core/test_verification.py` fails before the
   change, and the completion report shows that red run. After the change it passes,
   with relationship `DERIVED_SUPPORT` and reason `OPENAPI_POINTER_DERIVATION_MATCH`,
   for an error `/code` claim `"400"` proven by `/paths/~1payments/post/responses/400`.
2. Each of these is refused and never produces support. Each case has a test, and the
   completion report states the reason code for each:
   1. the response key is `200`;
   2. the response key is `default`;
   3. the response key is `4XX`;
   4. the response key is `401` but the claim's code is `"400"`;
   5. the pointer is not exactly `/paths/<p>/<m>/responses/<status>`, for example
      `/paths/~1payments/post/responses/400/description`;
   6. the claim kind is not `error`, for example an `operation` claim at `/code`.
3. The derivation name, version `"1"`, is added to `_ALLOWED_DERIVATIONS`
   (`loop_apidoc/core/verification.py`) and to the dispatch in
   `loop_apidoc/core/openapi_derivation.py`. `_openapi_pointer_derivation_name` in
   `loop_apidoc/shadow/bridge.py` selects it only for claim kind `error`, claim path
   `/code`, and a response pointer, and a test in `tests/shadow/test_bridge_claims.py`
   covers that selection. Existing selections stay unchanged.
4. Existing tests pass unchanged: `git diff main...HEAD -- tests/` adds tests only and
   edits no existing assertion.
5. A reproduction outside the repository uses the adyen snapshot
   (`benchmarks/adyen-payments-multimethod/sources/CheckoutService-v71.json`, SHA-256
   `9e426ae2bf007b148c393c5f163bbb0abe54959172b4d85676aedbd178b2b0b0`). It binds evidence
   in a scratch copy of the extraction to the 5 error `/code` claims, using the
   `/payments` response pointers, and runs the shadow pipeline. All 5 bindings are
   `derived_support`. The script and its output are in the completion report.
6. `wc -l` reports at most 800 lines for `loop_apidoc/core/openapi_pointers.py`,
   `loop_apidoc/core/openapi_derivation.py`, and `loop_apidoc/core/verification.py`. If
   a module would exceed 800, stop and report rather than split it inside this Story.
7. `git diff --name-status main...HEAD` lists only those three Core modules,
   `loop_apidoc/shadow/bridge.py`, test files under `tests/core/` or `tests/shadow/`, and
   this Story file (`specs/stories/core-error-code-derivation.md`).
8. `make verify` exits 0.
