# Developer Handoff Pack — Design

**Date:** 2026-06-30
**Status:** Approved for planning
**Topic:** Add a default downstream-engineer handoff pack to each `assemble`
run without turning it into a second API contract.

## Motivation

`loop-apidoc` already produces the contract and audit artifacts a source-grounded
API documentation run needs:

- `openapi.yaml`
- `api-guide.zh-TW.md`
- `review.html`
- `provenance.json`
- `integration-contract.json`
- `examples/`
- `validation/report.{json,md}`
- `preparation-report.{json,md}`

For a downstream integration engineer, these artifacts answer "what did the
source say?" and "is this output trustworthy?" They do not fully answer "what do
I implement first?", "which runtime values must my application provide?", "where
does signing or callback verification fit?", or "can I import this into a tool
and start checking request shape?"

The missing piece is a small developer handoff pack: a set of derived helper
artifacts that guide implementation, tool import, and SDK/client organization
while continuing to treat `openapi.yaml` and `integration-contract.json` as the
contract sources.

## Goals

1. Generate a `handoff/` directory by default on every `assemble` run.
2. Keep handoff artifacts derived-only: no new source facts, no guessed sample
   values, and no second copy of the API schema.
3. Help integration engineers start implementation by showing order, blockers,
   runtime config needs, and links to the authoritative artifacts.
4. Provide a Postman Collection adapter for quick manual request-shape testing.
5. Provide a compact `sdk-hints.json` for future client/SDK generation or agent
   consumption.
6. Keep implementation compatible with the existing `generate/` pure-function
   layer and single file-I/O exit.

## Non-Goals

- No replacement for `openapi.yaml`.
- No duplicate request/response schema documentation in Markdown or JSON.
- No generated SDK/client source code.
- No invented example values such as `"string"`, `0`, `true`, fake money
  amounts, fake tokens, or guessed base URLs.
- No automatic Postman pre-request scripts in the first version unless the
  source-grounded integration contract is complete enough to support them. The
  first version should prefer clear placeholders and links over pseudo-working
  scripts.
- No direct dependency on `validation/report.json` during handoff generation.
  The current pipeline generates outputs before validation, so handoff links to
  the validation report instead of embedding it.

## Product Shape

Every successful or validation-failed `assemble` run should still write the
handoff pack, because a failed validation run can contain useful engineering
context and blockers.

```text
output/<run-id>/
└── handoff/
    ├── integration-tasks.md
    ├── postman_collection.json
    └── sdk-hints.json
```

The pack is a developer-facing adapter over the primary artifacts:

| Artifact | Primary question answered | Must not do |
| --- | --- | --- |
| `openapi.yaml` | What is the API contract? | Plan implementation work |
| `integration-contract.json` | What signing, encryption, callback, condition, or contract-test mechanisms did the source state? | Replace OpenAPI schema |
| `handoff/integration-tasks.md` | What should the engineer implement, configure, or unblock next? | Reprint full schema definitions |
| `handoff/postman_collection.json` | Can a request-shape collection be imported into Postman? | Become a second contract |
| `handoff/sdk-hints.json` | How should a generator or agent group operations and attach integration-mechanism dependencies? | Define new API semantics |

## Core Invariant

OpenAPI is the API contract. The handoff pack is engineering navigation and tool
adapter output.

If a piece of content can be fully expressed by OpenAPI, handoff should link to
the OpenAPI pointer rather than restating it. Handoff may summarize operation
identity (`operationId`, method, path), runtime requirements, source-stated
integration mechanisms, and missing/conflicting/unverified blockers, because
those are implementation-planning concerns.

## Architecture

Add one pure generation module:

```text
loop_apidoc/generate/handoff.py
```

Public seam:

```python
def build_handoff(
    openapi: dict,
    plan: NormalizationPlan,
    integration: dict | None,
) -> dict[str, str]:
    ...
```

The return value is a relative-path map:

```python
{
    "handoff/integration-tasks.md": "...",
    "handoff/postman_collection.json": "...",
    "handoff/sdk-hints.json": "...",
}
```

Wire it like `examples/`:

1. Add `handoff: dict[str, str] = Field(default_factory=dict)` to
   `GenerateResult`.
2. In `build_result`, build `openapi`, `integration`, and `examples`, then call
   `build_handoff(openapi, plan, integration)`.
3. In `generate_outputs`, iterate `result.handoff` and write the relative paths
   under the run directory.
4. In `review.html`, add a product-entry link to
   `handoff/integration-tasks.md`.

`handoff.py` must not perform file I/O, re-read `openapi.yaml`, or parse files it
just caused to be generated. It should use the in-memory `openapi` dict and the
already-built integration dict.

## Data Flow

```text
NormalizationPlan
      │
      ├── build_openapi(plan) ────────────────┐
      ├── build_integration_document(plan) ───┤
      └── plan gaps/conflicts/unverified ─────┤
                                               ↓
                                      build_handoff(...)
                                               ↓
                              handoff/*.md / *.json files
```

The validation report remains authoritative for validation status. Handoff links
to `../validation/report.md` but does not embed validation issues in the first
version. This preserves the current `generate -> validate -> write validation`
ordering.

## Artifact Details

### `integration-tasks.md`

This is a human-readable implementation checklist, not an API reference.

Required sections:

1. **Run Context**
   - Link to `../openapi.yaml`.
   - Link to `../integration-contract.json`.
   - Link to `../validation/report.md`.
   - Link to `../examples/README.md` when examples exist.
2. **Runtime Configuration**
   - Base URL variables such as `base_url`.
   - Auth variables from OpenAPI security schemes.
   - Integration keys/IVs/secrets from integration contract key sources when
     source-stated.
3. **Implementation Order**
   - One checklist item per operation or webhook.
   - Each item includes operation identity and OpenAPI pointer.
   - Each item links to generated examples when present.
   - Each item names required integration mechanisms, callbacks, or field
     conditions without expanding schema details.
4. **Integration Mechanisms**
   - Signing/encryption/callback tasks derived from
     `integration-contract.json`.
   - Each task links to the relevant JSON pointer.
5. **Blockers & Gaps**
   - `plan.missing_items`, `plan.source_conflicts`, `plan.unverified_items`, and
     `integration["missing"]`.
   - Mark each as `Blocked`, `Conflict`, `Unverified`, or `Gap`.

Example shape:

```markdown
# Developer Integration Tasks

## Run Context

- Primary contract: `../openapi.yaml`
- Integration mechanisms: `../integration-contract.json`
- Validation status: `../validation/report.md`
- Request examples: `../examples/README.md`

## Implementation Order

- [ ] Implement `createPayment` (`POST /payments`)
  - Contract: `../openapi.yaml#/paths/~1payments/post`
  - Example: `../examples/createPayment/request.ts`
  - Requires signing: `integration-contract.json#/crypto/0`

## Blockers & Gaps

- [ ] Blocked: source does not state AES padding for `TradeInfo`
```

The file should not contain complete request-body field tables, response schema
copies, or prose that competes with `api-guide.zh-TW.md`.

### `postman_collection.json`

This is a Postman Collection v2.1 adapter.

Rules:

- Collection name comes from OpenAPI `info.title`, falling back to
  `Untitled API`.
- Collection variables include `base_url`, using a source-stated base URL as the
  initial value when available and `<base_url>` otherwise.
- Each OpenAPI operation becomes one item.
- Item URL uses `{{base_url}}` plus the path.
- Params, headers, auth, and body are populated only with source-stated values or
  placeholders.
- Item descriptions link back to:
  - OpenAPI pointer.
  - Generated example path when present.
  - Integration contract pointer when the operation has related signing,
    encryption, callback, or condition dependencies.
- Request bodies must not fabricate type samples. Missing values become
  `<field_name>` placeholders.
- First version should not generate pre-request scripts unless all required
  crypto details are source-grounded. If details are incomplete, item description
  states the blocked mechanism and points to `integration-contract.json`.

The collection is for import and request-shape exploration. The source of truth
remains `openapi.yaml`.

### `sdk-hints.json`

This is compact machine-readable metadata for a future generator, code agent, or
manual SDK/client author.

It should link to contracts and describe grouping/dependencies without copying
schemas.

Example shape:

```json
{
  "version": "1.0",
  "contracts": {
    "openapi": "../openapi.yaml",
    "integration": "../integration-contract.json"
  },
  "operation_groups": [
    {
      "name": "Payments",
      "operations": ["createPayment"]
    }
  ],
  "implementation_notes": [
    {
      "operation_id": "createPayment",
      "method": "POST",
      "path": "/payments",
      "contract_pointer": "../openapi.yaml#/paths/~1payments/post",
      "example_paths": ["../examples/createPayment/request.ts"],
      "requires": ["runtime:base_url", "crypto:TradeInfo"],
      "gaps": []
    }
  ],
  "gaps": []
}
```

Allowed content:

- Contract links.
- Operation group labels from OpenAPI tags.
- Operation IDs, method, path, and pointers.
- Required runtime variables.
- Integration-mechanism dependency labels.
- Gaps/blockers.

Disallowed content:

- Full schema copies.
- Language-specific class definitions.
- Generated TypeScript/Python/PHP code.
- Semantics not present in OpenAPI or integration contract.

## Pointer Rules

OpenAPI pointers must be deterministic and JSON-pointer escaped:

- `/payments` path -> `../openapi.yaml#/paths/~1payments/post`
- `/v1/orders/{id}` path -> `../openapi.yaml#/paths/~1v1~1orders~1{id}/get`

Integration contract pointers use array indexes in the generated document:

- `../integration-contract.json#/crypto/0`
- `../integration-contract.json#/callbacks/0`
- `../integration-contract.json#/field_conditions/0`
- `../integration-contract.json#/test_cases/0`

Example links use the existing `operationId` directory convention:

- `../examples/{operationId}/request.sh`
- `../examples/{operationId}/request.ts`
- `../examples/{operationId}/request.py`

## Edge Cases

- **No operations:** still produce all three handoff files. Tasks say there are
  no source-grounded operations; Postman items and SDK operation notes are empty.
- **No source-stated base URL:** use `{{base_url}}` and list `base_url` as a
  runtime configuration task.
- **No integration mechanisms:** keep the integration contract link but state no
  source-grounded signing, encryption, callback, condition, or test-case
  mechanisms were found.
- **Validation failure:** still produce handoff, because blockers are useful.
  `integration-tasks.md` links to validation status instead of embedding it.
- **Missing `operationId`:** this should not happen because OpenAPI generation
  assigns operation IDs. If encountered, handoff may use a deterministic
  method/path fallback and record a generator gap in `sdk-hints.json`.
- **Webhooks:** include webhook operations in implementation order as callback
  receiver tasks and point to `../openapi.yaml#/webhooks/...`.

## Testing Strategy

Use TDD and keep tests focused on the handoff contract.

### `tests/generate/test_handoff_tasks.py`

- `integration-tasks.md` includes run-context links.
- It includes implementation-order checklist items with OpenAPI pointers.
- It includes runtime config tasks for base URL and auth.
- It includes crypto/callback/gap tasks when present.
- It does not include full request-body schema tables or response schema copies.

### `tests/generate/test_handoff_postman.py`

- Generated JSON follows Postman Collection v2.1 top-level shape.
- URLs use `{{base_url}}`.
- Item descriptions include OpenAPI pointers.
- Missing values become placeholders.
- Output does not contain fabricated type samples such as `"string"` as a value,
  numeric `0` as a guessed example, or boolean `true` as a guessed example.
- No pre-request script is emitted for incomplete crypto details.

### `tests/generate/test_handoff_sdk_hints.py`

- `sdk-hints.json` includes `contracts`, `operation_groups`,
  `implementation_notes`, and `gaps`.
- Operation notes include operation ID, method, path, OpenAPI pointer, and
  integration dependencies.
- The file does not copy OpenAPI schemas.

### Writer and Review Integration

- `generate_outputs()` writes all three `handoff/*` files.
- `GenerateResult` includes a `handoff` map.
- `review.html` links to `handoff/integration-tasks.md`.

## Acceptance Criteria

- Every `assemble` run writes:
  - `handoff/integration-tasks.md`
  - `handoff/postman_collection.json`
  - `handoff/sdk-hints.json`
- Handoff files are derived from `openapi`, `NormalizationPlan`, and
  `integration-contract` data only.
- Handoff does not duplicate full OpenAPI schemas.
- Missing source values render as explicit placeholders or blockers.
- `review.html` exposes a handoff entry point.
- README and `docs/ARCHITECTURE.md` document the new output directory and clarify
  that handoff is a derived engineering aid, not a contract source.
- Verification passes:
  - `uv run pytest`
  - `uv run ruff check .`
- At least one benchmark-like run with signing/callback data is manually
  spot-checked for:
  - checklist usefulness,
  - Postman importability,
  - compact and schema-free SDK hints.

## Future Work

- Add validation-aware handoff refresh after `validation/report.json` exists.
- Generate Postman pre-request scripts when crypto contract details are complete
  and covered by regression tests.
- Add an extraction-input diff or generator-note link for debugging why a
  handoff blocker appears.
- Compare handoff, Markdown, and generated examples in `loop-apidoc diff` once
  these artifacts have stable structured comparison rules.
