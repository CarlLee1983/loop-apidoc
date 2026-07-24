# Source Candidates for GraphQL and AsyncAPI Slices

**Status:** researched 2026-07-24; candidates await operator intake and
snapshotting.
**Purpose:** identify first-party or standards-body sources that can support
the planned GraphQL and AsyncAPI vertical slices without using synthetic
fixtures as source evidence.

## Recommendation

Use the GitHub public GraphQL schema for the GraphQL slice and the pinned OGC
API–EDR Pub/Sub AsyncAPI document for the AsyncAPI slice. Both must first be
downloaded as immutable, gitignored source snapshots with URL, retrieval time,
and SHA-256 recorded in the manifest. Neither live URL should be treated as a
historical version after snapshotting.

The OGC document is an official, machine-readable conformance example—not a
claim about a live production broker. It is appropriate for a standard-focused
AsyncAPI projection and validation fixture, but must not be reported as a
production integration benchmark.

## GraphQL candidate: GitHub public schema

- **Source:** [GitHub GraphQL public schema download](https://docs.github.com/public/fpt/schema.docs.graphql).
- **Authority:** GitHub’s [Public schema documentation](https://docs.github.com/en/graphql/overview/public-schema)
  explicitly publishes that SDL as the public schema for the GitHub GraphQL
  API.
- **Source facts available:** schema types, fields, input objects, enums, root
  operations, arguments, descriptions, lists, and nullability.
- **Named consumer:** GitHub documents [GitHub CLI `gh api graphql`](https://docs.github.com/en/graphql/guides/using-graphql-clients)
  as a GraphQL client; the same page describes schema introspection for client
  documentation/autocomplete. GraphQL Code Generator also accepts a local
  `.graphql` schema path as input ([schema configuration](https://the-guild.dev/graphql/codegen/docs/config-reference/codegen-config)).
- **Intake constraints:** the URL serves the latest schema, so record its raw
  bytes and SHA-256 before extraction. The GitHub page does not state a
  separate redistribution licence for the schema; retain the raw source only
  in the operator-provided, gitignored source directory and commit only
  derived fixtures/provenance permitted by repository policy.

## AsyncAPI candidate: OGC API–EDR Pub/Sub example

- **Source:** [Pinned AsyncAPI 3.0 YAML](https://raw.githubusercontent.com/opengeospatial/ogcapi-environmental-data-retrieval/88ed4ddee449db2ea60359a61eb3a1dff6a46c24/extensions/pubsub/standard/examples/yaml/asyncapi.yaml)
  from the [OGC API–EDR repository](https://github.com/opengeospatial/ogcapi-environmental-data-retrieval).
- **Authority:** the [OGC API–EDR Part 2 Publish-Subscribe Workflow standard](https://docs.ogc.org/is/23-057r1/23-057r1.pdf)
  is an approved OGC standard, identifies AsyncAPI 3.0.0 as a normative
  reference, and includes a Pub/Sub API description example. The pinned source
  is preferred over a branch URL because its Git revision is immutable.
- **Source facts available:** AsyncAPI version, MQTT server/security, channels,
  receive operations, message names, payload schemas, and required fields.
- **Named consumer:** an OGC API–EDR subscriber/data consumer; the standard
  defines a subscriber as the entity that creates a subscription to a
  publisher. For artifact validation and docs generation, the official
  [AsyncAPI Generator](https://www.asyncapi.com/tools/generator) is a concrete
  tooling consumer and supports documentation/code generation from AsyncAPI
  documents.
- **Intake constraints:** retain the OGC licence/notice with the operator
  snapshot. The YAML is an example, so preserve that classification in the
  benchmark notes and never imply that its host, broker credentials, or
  delivery semantics represent a deployed service.

## Proposed first source-backed tests

1. **GraphQL:** from the GitHub SDL, select a small closed set containing a root
   `Query` or `Mutation` field, its arguments, referenced type, and nullability.
   Prove `schema.graphql` preserves those facts and provenance maps each emitted
   element to an exact SDL fragment.
2. **AsyncAPI:** from the pinned OGC YAML, select one channel, its receive
   operation, one message, and payload-required fields. Prove `asyncapi.yaml`
   preserves channel/direction/message/payload facts and provenance maps each
   emitted element to an exact YAML fragment.

Do not fill an absent broker field, retry/acknowledgement setting, GraphQL
operation, or nullability from protocol convention. Such facts remain gaps.
