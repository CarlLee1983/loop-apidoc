# Derive body-parameter name and required claims from an inline request-body schema

## Goal

Core can prove a body parameter's `name` and `required` claims only when the operation's
request body is a named component. The supported forms today are a direct pointer into
`/components/schemas/<request_schema_ref>/properties/...`, the
`openapi_request_body_property_*` derivations in
`loop_apidoc/core/openapi_pointers.py`, and their `$ref`-linked variants. Both require
the operation's `request_schema_ref`.

OpenAPI also allows the request body schema to be written inline under
`/paths/<path>/<method>/requestBody/content/<media-type>/schema`. stripe's
`spec3.sdk.json` uses that form for every Payment Intents operation, so its 97 body
parameters (194 claims) stay `DERIVATION_INAPPLICABLE` or contradicted. This is one of
the three Core gaps that block stripe exact-evidence parity. B1 (#180) closed the first.

Add two version-1 derivations for direct properties of an inline request-body schema,
following the existing component-schema derivations:

- `openapi_inline_request_body_property_name_from_pointer`: the evidence is
  `.../requestBody/content/<media-type>/schema/properties/<name>`, and it proves
  `/parameters/body/<name>/name`.
- `openapi_inline_request_body_property_required_from_schema_pointer`: the evidence is
  the inline schema at `.../requestBody/content/<media-type>/schema`, and it proves
  `/parameters/body/<name>/required` from the schema's `required` array.

Each derivation proves a claim only for the operation the pointer names. The shadow
bridge proposes them for matching pointers. The strict path reaches the same bridge
through `execute_shadow`, so this does not extend shadow with behaviour that strict
lacks (ADR 0016).

## Out of Scope

- Nested inline properties (`properties/<a>/properties/<b>`), array `items`, and `$ref`
  hops inside an inline schema. If stripe needs any of them, stop and report.
- Body parameter `type` claims, security-requirement claims (B3), and inventory-level
  claims.
- Changing the existing component-schema or `$ref`-linked derivations, or their names
  and versions.
- Adding `evidence[]` to any committed benchmark, or changing
  `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`.

## Acceptance Criteria

1. TDD comes first. New tests in `tests/core/test_verification.py` mirror
   `test_openapi_request_schema_pointer_proves_direct_body_field_requiredness` and the
   matching name test. They fail before the change, and the completion report shows
   that red run. They pass after, with relationship `DERIVED_SUPPORT` and reason
   `OPENAPI_POINTER_DERIVATION_MATCH`, for:
   - a name claim proven by `/paths/~1v1~1things/post/requestBody/content/application~1x-www-form-urlencoded/schema/properties/amount`;
   - a `required: true` claim and a `required: false` claim proven by the inline schema
     pointer.
2. Each of these fails closed with `DERIVATION_INAPPLICABLE` or `EVIDENCE_VALUE_MISMATCH`
   (never support), and each has a test:
   1. the pointer names a different path or method from the claim's operation;
   2. the property is absent from the inline schema's `properties`;
   3. the claimed `required` flag disagrees with the schema's `required` array;
   4. the pointer goes through a nested property or `items`;
   5. the schema at the pointer is a `$ref` rather than an inline object;
   6. the operation declares a `request_schema_ref`, so the component derivation applies
      instead.
3. Both derivation names, version `"1"`, are added to `_ALLOWED_DERIVATIONS` in
   `loop_apidoc/core/verification.py` and to the dispatch in
   `loop_apidoc/core/openapi_derivation.py`. The shadow bridge's
   `_openapi_pointer_derivation_name` (`loop_apidoc/shadow/bridge.py`) returns them only
   for pointers under `/paths/<p>/<m>/requestBody/content/<mt>/schema`. A bridge-level
   test or an existing bridge test file covers that selection.
4. Existing tests pass unchanged: `git diff main...HEAD -- tests/` adds tests only and
   edits no existing assertion.
5. A reproduction outside the repository uses the stripe snapshot
   (`benchmarks/stripe-basic-rest/sources/spec3.sdk.json`, SHA-256 `a58d0f7c…7fe9e`). It
   binds v1 evidence to every body parameter's `name` and `required` claim in a scratch
   copy of the extraction and runs the shadow pipeline. All 194 of those claims come out
   `explicit_support` or `derived_support`, and none is `insufficient` or `contradicts`.
   The script and a per-relationship count are in the completion report.
6. `wc -l` reports at most 800 lines for `loop_apidoc/core/openapi_pointers.py`,
   `loop_apidoc/core/openapi_derivation.py`, and `loop_apidoc/core/verification.py`.
7. `git diff --name-status main...HEAD` lists only those three core modules,
   `loop_apidoc/shadow/bridge.py`, test files under `tests/core/` or `tests/shadow/`, and
   this Story file (`specs/stories/core-inline-request-body-derivation.md`).
8. `make verify` exits 0.
