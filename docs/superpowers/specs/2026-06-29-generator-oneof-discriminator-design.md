# Generator `oneOf` / `discriminator` Support — Design

**Date:** 2026-06-29
**Status:** Approved (design)
**Topic:** Native OpenAPI `oneOf` + `discriminator` generation for polymorphic
(multi-product, shared-endpoint) request bodies and schema fields.

## Motivation

The benchmark validation set (`docs/BENCHMARK_VALIDATION_PLAN.md`, round 2) surfaced
the pipeline's one remaining faithful limitation. `adyen-payments-multimethod` has a
single `POST /payments` whose `paymentMethod` body field is a `oneOf` union over 40+
payment-method detail objects, selected by a `type` discriminator. The current
generator cannot emit native OpenAPI `oneOf`/`discriminator`, so it degrades the field
to `{"type": "object"}` plus a prose note and three separately-named member schemas.
That is faithful (recorded in `missing`, not speculation) but it loses machine-usable
polymorphism: a codegen consumer cannot see that `paymentMethod` is one of N concrete
shapes.

This feature lets the extraction declare a field as a union of already-named member
schemas, and lets the generator emit native `oneOf` (+ optional `discriminator`) that
points at those members by `$ref`. It closes the limitation without weakening the
source-grounded invariant.

## Scope

In scope (seven items):
1. Extraction contract (`SKILL.md` §3) — optional `one_of` / `discriminator` on a field.
2. Plan model — no change (verified: `parameters` / `fields` are `list[dict]` passthrough).
3. Generator `openapi.py` — emit `oneOf` + `discriminator`; thread `name_to_key` into
   the body/schema property-building path.
4. Generator `markdown.py` — render the union readably in `api-guide.zh-TW.md`.
5. No-speculation / provenance — no change (verified: nested nodes are not assertion targets).
6. Re-ground the `adyen-payments-multimethod` benchmark to use the new representation.
7. Tests (TDD) — generator unit tests + a focused assertion on the adyen output;
   keep the benchmark harness green.

Out of scope:
- Examples generator (`examples.py`) — `paymentMethod` stays a `<placeholder>`; grounded
  request examples continue to live in `integration.test_cases`.
- `anyOf` / `allOf` — only `oneOf` is in scope.
- Schema-level named union entries (a `SchemaEntry` that is itself a union). Field-level
  `one_of` is the only mechanism; this matches Adyen's inline-`oneOf`-on-field shape and
  keeps a single contract surface (YAGNI).

## Core invariant (unchanged)

The source is the only ground truth. `oneOf` is emitted **only** when the extraction
declares `one_of` (i.e. the source documents the field as a union of those member
shapes). `discriminator` is emitted **only** when the extraction supplies it. Member
names that do not resolve to a named, source-grounded schema are dropped — a dangling
`$ref` is never invented (same rule as response `schema_ref`).

## 1. Extraction contract (`SKILL.md` §3)

An `in:body` parameter, or a `schemas[].fields` entry, MAY carry two optional keys:

```json
{
  "name": "paymentMethod", "in": "body", "type": "object", "required": true,
  "one_of": ["CardDetails", "IdealDetails", "ApplePayDetails"],
  "discriminator": {
    "property_name": "type",
    "mapping": {"scheme": "CardDetails", "ideal": "IdealDetails", "applepay": "ApplePayDetails"}
  },
  "description": "..."
}
```

- `one_of`: a list of schema **names**, each of which MUST also appear as a named entry
  in `inventory.schemas` (so each member is independently captured and provenance-backed).
- `discriminator` (optional): `property_name` is the source-stated discriminating
  property (e.g. `type`); `mapping` maps each discriminator value to a member schema
  **name**. Omit `discriminator` entirely when the source states no explicit discriminator.

Grounding rule (added to the SKILL contract): declare `one_of` only when the source
documents the field as one of those member shapes; never synthesize a union from
REST/payment conventions. Key naming is snake_case (`one_of`, `property_name`),
consistent with existing extraction keys.

## 2. Plan model — no change

`EndpointEntry.parameters` and `SchemaEntry.fields` are `list[dict]` and the builder
carries each dict verbatim (`item.get("parameters")`, `i.get("fields")`). The new
`one_of` / `discriminator` keys ride along inside the field dict with no model edit.

## 3. Generator — `openapi.py`

### `_union_schema(field, name_to_key) -> dict | None`

New pure helper:

- If `field` has no truthy `one_of` → return `None`.
- Resolve each name in `one_of` through `name_to_key`; build
  `members = [{"$ref": f"#/components/schemas/{key}"}]` for every name that resolves.
  Drop names that do not resolve.
- If `members` is empty → return `None` (caller falls back to the existing
  `{"type": "object"}` shape; no fabricated union).
- Result: `{"oneOf": members}`. Carry `field["description"]` onto the result if present.
- If `field` has a `discriminator` dict with a truthy `property_name`, add
  `{"discriminator": {"propertyName": property_name}}`. If `discriminator.mapping` is
  present, build `mapping = {value: f"#/components/schemas/{key}"}` for each value whose
  target name resolves through `name_to_key`; drop unresolvable targets; include
  `mapping` only if non-empty.

### Threading `name_to_key`

`name_to_key` currently reaches responses only. Extend it into the property/body path so
a leaf field's `one_of` can resolve member `$ref`s:

- `_property_schema(field, name_to_key)` — when `_union_schema(field, name_to_key)`
  returns a union, return it instead of the plain `_schema_from_type` fragment.
- `_node_schema` / `_materialize_node` / `_nest_properties` — accept and forward
  `name_to_key` so leaf fields are built through the union-aware `_property_schema`.
- `_build_request_body(request, body_params, name_to_key)` and
  `_build_object_schema(entry, name_to_key)` — accept `name_to_key` and pass it down.
- Call sites in `_build_operation` / `_build_schemas` pass the existing `name_to_key`.

A union leaf is terminal: a field carrying `one_of` is not also expanded as a nested
dotted-path object (members already describe the shape).

## 4. Generator — `markdown.py`

`_field_line` (the per-field bullet): when `field.get("one_of")`, replace the
`型別 \`object\`` bit with `oneOf：CardDetails / IdealDetails / ApplePayDetails`
(member names joined by ` / `). When a `discriminator.property_name` is present, append
`判別子 \`type\``. Required flag, description and indentation are unchanged. This is the
"文件可讀性" payoff — a reader sees the concrete alternatives on one line.

## 5. No-speculation / provenance — no change

`check_speculation` enumerates only top-level assertion targets (`info.*`, `servers[]`,
`components.securitySchemes.*`, `paths.{path}.{method}`, `components.schemas.{name}`) and
does not walk nested properties. `oneOf` / `discriminator` live **inside** a body or
schema node, so they create no new target. Each member `$ref` points at a
`components.schemas.{name}` that already has its own provenance entry. The union is
therefore grounded transitively with no provenance or speculation-check change.

## 6. Re-ground the `adyen-payments-multimethod` benchmark

- `extraction/endpoints/ep0.json` — `paymentMethod` gains `one_of`
  (`CardDetails`, `IdealDetails`, `ApplePayDetails`) and `discriminator`
  (`property_name: type`, mapping `scheme/ideal/applepay → member`). Its endpoint-level
  `missing` note about oneOf is removed.
- `extraction/inventory.json` — remove the "paymentMethod is a oneOf union … the
  pipeline does not emit native OpenAPI oneOf" item from `missing`; adjust the
  `PaymentRequest.paymentMethod` description so it no longer says "this benchmark
  captures three representative members" as a limitation.
- `expected/validation.expect.json` — flip the lead observation from "忠實限制" to
  "原生 oneOf/discriminator 正面證明"; `expected/minimum.json` `_note` likewise.
- `notes.md` — update the "忠實限制" section: oneOf is now natively emitted (CSE
  algorithm and webhook/HMAC remain genuine `missing`).
- Re-run `assemble`: expected result is unchanged status — **PASS with the same 3
  `REQUIRED_INFO_MISSING.warning`** (endpoint inline examples). `current_issue_classes`
  stays `{"REQUIRED_INFO_MISSING.warning": 3}`, so the hardened harness stays green.

## 7. Tests (TDD)

Unit tests (write first, watch fail, implement):

- `openapi.py`:
  - field with `one_of` (members resolvable) → body/schema property is
    `{"oneOf": [{"$ref": ".../CardDetails"}, ...]}` (+ description preserved).
  - `discriminator` present → `discriminator.propertyName` + resolvable `mapping`
    entries as `$ref`s; unresolvable mapping targets dropped.
  - one unresolvable member name → dropped from `oneOf`, others kept.
  - all member names unresolvable → field falls back to `{"type": "object"}`.
  - union works both as an `in:body` parameter and as a `schemas[].fields` entry.
- `markdown.py`: a `one_of` field renders the `oneOf：A / B / C` bullet (+ `判別子`).
- Benchmark: the existing `tests/test_benchmarks.py` re-runs adyen and stays green
  (status + issue-class map unchanged). Add a focused unit test that builds the adyen
  OpenAPI and asserts `paths./payments.post` request body contains a `oneOf` with the
  three member `$ref`s and a `discriminator.propertyName == "type"`.

The committed `extraction/` is the regression fixture; the openapi-spec-validator step
in the harness already structurally validates the emitted `oneOf` / `discriminator`.

## Risks & mitigations

- **Plumbing reach.** Threading `name_to_key` touches several private builders. Mitigated
  by keeping each signature change additive (new trailing param, default-free internal
  calls) and covering each builder with the unit tests above.
- **Accidental union for plain object fields.** `_union_schema` returns `None` unless
  `one_of` is truthy, so existing `type: object` fields are untouched (regression-guarded
  by the all-unresolvable and no-`one_of` tests).
- **Discriminator without `oneOf`.** If `discriminator` is supplied but `one_of` is
  absent/empty, no union is emitted and `discriminator` is ignored (it is only attached
  to a non-empty `oneOf`).

## Acceptance

- Generator emits valid OpenAPI 3.1 `oneOf` (+ `discriminator` when declared) for a
  `one_of` field; degrades to `{"type": "object"}` when no member resolves.
- `api-guide.zh-TW.md` renders the union members on the field line.
- `adyen-payments-multimethod` PASSes with native `oneOf`, same 3 warnings; full suite
  and benchmark harness green.
- No change to `speculation.py`, `provenance.py`, or the plan models.
