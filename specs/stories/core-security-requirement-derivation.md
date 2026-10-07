# Derive operation security and security-scheme name claims from OpenAPI security objects

## Goal

Core represents an operation's security as one claim per scheme,
`/security/<scheme>` with the scheme name as its value (`loop_apidoc/domain/claim_paths.py`,
operation paths). It represents a security scheme's identity as the `/name` claim of a
`security` entry. OpenAPI states these differently:

- A security requirement is an object such as `{"bearerAuth": []}`. It sits in the
  operation's own `security` list, or, when the operation declares none, in the
  document-level `security` list that applies to it.
- A scheme's name is the key under `/components/securitySchemes/<key>`.

No derivation maps either form to the claim. Binding the claim to the object yields
`EVIDENCE_VALUE_MISMATCH`, an object compared against a string. stripe's
`spec3.sdk.json` declares `security: [{"basicAuth": []}, {"bearerAuth": []}]` at document
level and no operation-level security. So its 12 operation security claims and 2
scheme-name claims cannot be supported. This is the last of the three Core gaps that
block stripe exact-evidence parity. B1 (#180) closed the first and B2 (#181) the second.

Add three version-1 derivations, each failing closed:

- `openapi_security_scheme_name_from_pointer`: the evidence is
  `/components/securitySchemes/<key>`, and it proves the `security` claim `/name` = `<key>`.
  It mirrors `openapi_schema_name_from_pointer`.
- `openapi_operation_security_from_operation_requirement`: the evidence is
  `/paths/<p>/<m>/security/<i>`, and it proves `/security/<scheme>` for that operation.
- `openapi_operation_security_from_document_requirement`: the evidence is `/security/<i>`
  plus one context fragment, the operation object `/paths/<p>/<m>` from the same
  artifact. The context fragment proves the operation declares no `security` of its
  own, so the document-level requirement is the one that applies. This is a bounded
  two-fragment form, like the existing `$ref`-linked derivations.

For both requirement derivations, the requirement object must hold exactly one scheme
key, equal to the claimed scheme, with an empty scope list.

## Out of Scope

- Requirement objects with several keys (AND semantics), non-empty scope lists, and the
  empty requirement `{}` (anonymous access). Each one is refused, never supported.
- Security-scheme `type`, `location`, and `details` claims, and every other
  inventory-level claim.
- Changing the existing derivations, or Core's claim model for security.
- Adding `evidence[]` to any committed benchmark, or changing
  `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`.
- Starting implementation before #181 is merged. B2 touches the same three Core modules
  and the bridge.

## Acceptance Criteria

1. TDD comes first. New tests in `tests/core/test_verification.py` fail before the change,
   and the completion report shows that red run. They pass after, with relationship
   `DERIVED_SUPPORT` and reason `OPENAPI_POINTER_DERIVATION_MATCH`, for:
   - a scheme `/name` claim proven by `/components/securitySchemes/bearerAuth`;
   - an operation `/security/bearerAuth` claim proven by an operation-level requirement;
   - an operation `/security/bearerAuth` claim proven by a document-level requirement
     plus the operation-object context fragment.
2. Each of these is refused and never produces support. Where an existing derivation
   has an equivalent case, the refusal uses that derivation's reason code; otherwise it
   uses `DERIVATION_INAPPLICABLE` or the code the verifier already uses for an invalid
   context. Each case has a test, and the completion report states the code for each:
   1. the requirement's single key differs from the claimed scheme;
   2. the requirement has more than one key;
   3. the requirement's scope list is not empty;
   4. the requirement is the empty object `{}`;
   5. an operation-level pointer names a different path or method from the claim's
      operation;
   6. a document-level requirement has no context fragment, has a context fragment from
      another artifact, or has a context operation object that declares its own
      `security`;
   7. a document-level requirement's context operation names a different path or method
      from the claim's operation;
   8. a scheme-name pointer is not exactly `/components/securitySchemes/<key>`.
3. All three derivation names, version `"1"`, are added to `_ALLOWED_DERIVATIONS`
   (`loop_apidoc/core/verification.py`) and to the dispatch in
   `loop_apidoc/core/openapi_derivation.py`. The document-level derivation joins the set
   that accepts context fragments. `_openapi_pointer_derivation_name` in
   `loop_apidoc/shadow/bridge.py` selects them only for the matching claim paths and
   pointer shapes, and a test in `tests/shadow/test_bridge_claims.py` covers that
   selection. Existing selections stay unchanged.
4. The extraction contract documents the new two-fragment form next to the existing
   approved multi-fragment forms in `skills/loop-apidoc/reference/extraction-schemas.md`:
   the document-level requirement fragment first, then the operation object, both with
   the same claim path.
5. Existing tests pass unchanged: `git diff main...HEAD -- tests/` adds tests only and
   edits no existing assertion.
6. A reproduction outside the repository uses the stripe snapshot
   (`benchmarks/stripe-basic-rest/sources/spec3.sdk.json`, SHA-256 `a58d0f7c…7fe9e`). It
   binds evidence in a scratch copy of the extraction to the 12 operation
   `/security/<scheme>` claims (document-level form) and the 2 scheme `/name` claims, and
   runs the shadow pipeline. All 14 claims are `derived_support`. The script and the
   per-relationship counts before and after are in the completion report.
7. `wc -l` reports at most 800 lines for `loop_apidoc/core/openapi_pointers.py`,
   `loop_apidoc/core/openapi_derivation.py`, and `loop_apidoc/core/verification.py`. If
   a module would exceed 800, stop and report rather than split it inside this Story.
8. `git diff --name-status main...HEAD` lists only those three Core modules,
   `loop_apidoc/shadow/bridge.py`, `skills/loop-apidoc/reference/extraction-schemas.md`,
   test files under `tests/core/` or `tests/shadow/`, and this Story file
   (`specs/stories/core-security-requirement-derivation.md`).
9. `make verify` exits 0.
