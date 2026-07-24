# Protocol Expansion Design: GraphQL and AsyncAPI

**Status:** Core transport seam and minimal source-backed GraphQL/AsyncAPI
projection slices delivered; provenance, validation, guides, and CLI artifacts remain
pending.
**Updated:** 2026-07-24

## Purpose

This design extends loop-apidoc from an HTTP/OpenAPI-oriented compatibility
pipeline to a source-grounded, multi-protocol contract product. It covers
GraphQL and AsyncAPI without weakening the product invariant: a source is the
only authority for a factual claim. An omitted schema, transport setting, or
delivery semantic remains `null` or a recorded gap; it is never inferred from
protocol convention.

This is deliberately a Core-first design. The current agent-native extraction
and `assemble` flow remains a compatibility adapter until equivalent
source-grounded behavior has been demonstrated.

## Outcomes and artifact contract

The format selected by a contract determines its machine-readable artifact and
reader guide. Review, provenance, and validation remain common artifacts.

| Contract format | Machine-readable artifact | Reader guide | Shared evidence artifacts |
| --- | --- | --- | --- |
| HTTP | `openapi.yaml` | `api-guide.zh-TW.md` | `review.html`, `provenance.json`, `validation/report.{json,md}` |
| GraphQL | `schema.graphql` | `graphql-guide.zh-TW.md` | `review.html`, `provenance.json`, `validation/report.{json,md}` |
| AsyncAPI | `asyncapi.yaml` | `asyncapi-guide.zh-TW.md` | `review.html`, `provenance.json`, `validation/report.{json,md}` |

All generated product guides remain Traditional Chinese. This design and the
canonical architecture documentation remain English-primary.

## Public seam

The public seam is the canonical, immutable `GroundedApiContract` consumed by
the existing `ProjectionCompiler.compile(contract)` interface. It must describe
interactions and data types without requiring callers to know HTTP, GraphQL, or
broker-specific implementation details.

The first implementation change is a protocol/transport layer in Domain:

```text
source-grounded claims
        ↓
Canonical API Contract
  • protocol-neutral interactions
  • reusable data types and messages
  • transport bindings
  • evidence bindings, gaps, conflicts
        ↓
protocol projection adapters
  HTTP/OpenAPI | GraphQL | AsyncAPI
```

An interaction has a stable identity, interaction mode, input/output type
references, security references, and evidence. Its transport binding supplies
the address and protocol-specific semantics. The initial modes are
`request_reply`, `publish`, `subscribe`, and `stream`.

Transport bindings are typed adapters, not optional fields spread across the
contract:

- **HTTP:** method, path, server, parameters, and response status semantics.
- **GraphQL:** operation kind (`query`, `mutation`, `subscription`), root-field
  name, arguments, and type nullability/input-output role.
- **AsyncAPI:** protocol/binding, channel or topic, publish/subscribe direction,
  message name, payload, headers, and server/broker reference.

The existing HTTP `Operation(method, path, responses)` model is a compatibility
shape. Phase 1 introduces the protocol-neutral representation and projects it
back to the same OpenAPI output before any GraphQL or AsyncAPI adapter ships.
No `if protocol == ...` branches may be added to the OpenAPI generator,
validation, or legacy extraction parser to simulate this seam.

## Canonical type and evidence rules

The type model must be expressive enough for all three projections: scalar,
object, input object, enum, list, named reference, requiredness/nullability,
and field-level evidence. A GraphQL SDL type and an AsyncAPI JSON-Schema
payload are projections of the same source-backed type facts; neither becomes
more authoritative than the other.

Every material interaction, address, direction, message, type, field, and
security declaration requires a claim path and evidence relationship. Target
namespaces prevent protocol ambiguity:

- `openapi:paths./payments.post.summary`
- `graphql:Mutation.createPayment.arguments.amount`
- `asyncapi:orders.status.changed.subscribe.message.OrderStatusChanged.payload.status`

Targets remain stable, deterministic, and one-to-one with their projected
artifact location. Unsupported, contradictory, stale, or ambiguous evidence
continues to fail closed.

## Validation and compatibility

Each projection owns structural validation against its format. Shared
validation verifies source grounding, claim/evidence reachability, type
reference resolution, cross-artifact consistency, and no-speculation rules.

HTTP/OpenAPI output must remain byte-for-byte stable for existing canonical
fixtures unless a separately approved compatibility change intentionally
alters it. The first protocol-seam test is therefore an HTTP parity test at the
`ProjectionCompiler.compile` seam—not a test of a private model conversion.

`diff` and `score` evolve only after both format slices exist:

- compare projected artifacts by format while preserving their common
  breaking/additive/changed/source-only classification;
- rename the internal score category from `openapi_validity` to
  `spec_validity` only through a versioned, backward-compatible score report;
- record artifact formats and projection-compiler versions in Foundry asset
  metadata.

## Delivery plan and acceptance evidence

### Phase 1 — Core seam and HTTP parity

1. Document and model protocol-neutral interactions, typed transport bindings,
   and generalized type facts in `domain/`.
2. Write one failing public projection test using an existing HTTP contract and
   a known-good OpenAPI payload.
3. Implement only enough migration/projection behavior to make that test pass.
4. Run the affected domain tests, then the Core suite and Ruff.

**Done when:** existing HTTP canonical fixtures preserve their OpenAPI
projection and evidence targets; no GraphQL or AsyncAPI production artifacts
exist yet.

**Progress (2026-07-24):** `GroundedApiContract` now accepts immutable
`Interaction` values through a discriminated HTTP/GraphQL/AsyncAPI transport
binding union. The Core builder routes source claims into interactions, Domain
rules apply common evidence requirements, and the OpenAPI compiler projects an
HTTP interaction with existing output semantics. A non-HTTP interaction causes
an explicit unsupported-projection error rather than an invented HTTP path.
The material claim-path projection now binds GraphQL transport, operation kind,
and root field separately; it binds AsyncAPI transport, channel, direction, and
message name separately; HTTP retains method/path/parameter/response paths.
GraphQL SDL and AsyncAPI output remain isolated from the HTTP compatibility
projection; their minimal, source-backed adapters are delivered by Phases 2 and 3.

### Phase 2 — GraphQL vertical slice

Prerequisite: one operator-provided GraphQL source set and one confirmed
downstream SDL or GraphQL-tooling consumer.

1. Add a source-backed fixture covering a query or mutation, arguments, output
   type, and an explicit missing fact.
2. Add a failing test at the projection seam for `schema.graphql` and GraphQL
   provenance targets.
3. Implement a GraphQL projection adapter and its structural validator.
4. Generate `graphql-guide.zh-TW.md`, review data, and provenance from the same
   canonical claims.

**Done when:** SDL parses, every emitted material element maps to exact
evidence, and absent source facts are visible as gaps rather than fabricated
SDL defaults.

**Progress (2026-07-24):** a GitHub public-schema snapshot provides the
`Query.viewer: User!` slice, including the documented `User.login: String!` and
`User.name: String` fields. `GraphqlProjectionCompiler` emits deterministic SDL
from a typed GraphQL interaction. Exact line evidence maps to the stable
`graphql:Query.viewer` provenance target, and an unresolved output schema
reference fails closed. Argument handling, reader-guide generation, and CLI/run
integration are still pending.

### Phase 3 — AsyncAPI vertical slice

Prerequisite: one operator-provided event source set and one confirmed broker
or AsyncAPI consumer.

1. Add a source-backed fixture for a channel/topic, direction, message,
   payload, and an explicit missing broker or binding fact.
2. Add a failing test at the projection seam for `asyncapi.yaml` and AsyncAPI
   provenance targets.
3. Implement an AsyncAPI projection adapter and structural validation.
4. Generate `asyncapi-guide.zh-TW.md`, review data, and provenance from the
   same canonical claims.

**Done when:** channel/message direction and payload references validate, and
undocumented delivery semantics are reported as gaps.

**Progress (2026-07-24):** an OGC-pinned AsyncAPI 3.0 conformance example
provides the `notify-collections` receive slice, its `collections` address,
`collection_msg` payload, and documented required fields. `AsyncApiProjectionCompiler`
emits deterministic AsyncAPI YAML from a typed AsyncAPI interaction. Exact-evidence
provenance maps the payload claim to the stable
`asyncapi:notify-collections.receive.message.collection_msg.payload` target.
Structural validation beyond this slice, the reader guide, and CLI/run integration are
still pending.

## Source intake contract for the format slices

The source snapshot must be placed in the requested run or benchmark source
directory and included in its manifest; a public URL alone is not sufficient
evidence. The operator also supplies the intended consumer so the output
format and validation command are explicit before implementation begins.

| Slice | Required source facts | Consumer confirmation | Fail-closed treatment |
| --- | --- | --- | --- |
| GraphQL | SDL or equivalent source describing root operation kind/name, arguments, output/input types, enum values, list/nullability where applicable, and security if documented | SDL loader, code generator, gateway, or another named GraphQL tool | Unknown nullability, scalar mapping, root field, argument, or auth stays absent/missing; no REST conversion |
| AsyncAPI | A spec or source describing server/broker when documented, channel/topic, publish/subscribe direction, message name, payload, headers, bindings/security when documented | Broker/tooling/runtime that consumes AsyncAPI 3.x | Unknown protocol/binding, acknowledgement, retry, retention, security, or payload field stays absent/missing |

The first source-backed test for each slice must cite exact fragments from this
snapshot. A tutorial excerpt, a freshly invented schema, an unavailable URL,
or a newer replacement document cannot stand in for the supplied source.

### Phase 4 — cross-format operations

Extend `assemble`, review, diff, score, Foundry metadata, skill instructions,
and English-primary/Traditional-Chinese-secondary teaching documents. Every
format must retain the same explicit approval and fail-closed governance path.

## Non-goals

- Converting GraphQL schemas into invented REST endpoints or AsyncAPI channels
  into invented HTTP paths.
- Guessing GraphQL nullability, event delivery guarantees, broker bindings,
  acknowledgements, retries, retention, or authentication.
- Changing legacy `assemble` behavior before HTTP parity is proven.
- Beginning GraphQL or AsyncAPI feature work without real source material and
  an identified downstream consumer.

## Decision record

This document refines the protocol-expansion constraint in
[PRODUCT_EXTENSION_ROADMAP.md](PRODUCT_EXTENSION_ROADMAP.md). The chosen seam
is the canonical contract plus projection compiler, because it centralizes
source-grounding, evidence, governance, and type rules. Format-specific
adapters gain leverage from that shared behavior while keeping protocol details
local.

---

## 繁體中文摘要

先把 Canonical API Contract 擴充為協定中立的 interaction、type 與 typed transport
binding，再以獨立 projection adapter 輸出 OpenAPI、GraphQL SDL 或 AsyncAPI。第一個
程式 slice 只驗證 HTTP/OpenAPI 相容性；GraphQL 與 AsyncAPI 要各自具備真實來源集和下游
consumer 才開始。所有格式共用 evidence、provenance、review、validation 與 fail-closed
規則；來源未明示的 nullability、broker binding、ack/retry 等資訊只能記為缺口，不能猜測。
