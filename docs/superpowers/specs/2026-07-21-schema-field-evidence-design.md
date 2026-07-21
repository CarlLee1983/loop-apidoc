# Schema Field Evidence Design

**Date:** 2026-07-21

## Goal

Make a source citation attached to `inventory.json` `schemas[].fields[]` a
first-class, fail-closed evidence claim that remains traceable to the exact
OpenAPI property it generated. Resolve manifest selection issue #18 by treating
the existing single-file `--sources` input as the supported precise-selection
workflow rather than adding a second filtering mechanism.

## Context

The agent input guard currently rejects a field-level `source` key because
`FieldEntry` forbids unknown keys. Even if it were only ignored, the citation
would disappear before the plan, provenance, and validation stages. That would
violate the source-grounded pipeline invariant: a source statement must either
be represented and verified or left absent, never silently discarded.

The schema-level `source` remains the citation for the schema declaration.
Field-level citations state support for an individual property. They are
optional, so existing extraction inputs remain valid and a schema citation can
continue to support fields that carry no more precise citation.

## Design

### Input boundary and source guard

`agentcli.input_schema.FieldEntry` accepts an optional string `source` while
retaining strict rejection of all other unknown non-extension keys. The source
guard collects citations from `schemas[i].fields[j].source` as part of
`inventory.json`'s citation scope. It applies the existing per-file rule:
when a multi-source manifest has no citation in that scope that names a manifest
source, boundary verification fails; partially resolvable citations continue to
be represented and fail later per claim as `SOURCE_UNVERIFIED`.

### Normalization plan

Add a typed field-evidence record to `plan.models` with:

- the extraction field name;
- the `PlanItemStatus` returned by `classify_item`;
- its exact `SourceCitation` list.

Each `SchemaEntry` stores a list of these records alongside its existing raw
`fields`. During stage 07 plan construction, the builder classifies every
field-level `source` and creates an evidence record only when the field has a
non-empty source string. It also records an `UnverifiedItem` for any
unresolved field claim. The raw field dictionary remains unchanged for the
OpenAPI generator, so property generation keeps its current contract.

### Provenance and validation

Provenance emits a record for every field-evidence item whose field produces an
OpenAPI property. Its target is the generated property location, for example
`components.schemas.Payment.properties.amount`. The target calculation follows
the existing dotted-name convention used by `_nest_properties`:

- `customer.id` becomes `...properties.customer.properties.id`;
- `items[].sku` becomes `...properties.items.items.properties.sku`;
- a terminal `items[]` is the `...properties.items` array property.

No property target is created for malformed/empty field names that do not
produce an OpenAPI property. Such input is already governed by existing schema
generation and validation behavior; this feature does not invent a property.

The speculation validator traverses emitted schema properties (including
nested object and array-item properties) and requires provenance for each
asserted property. A property with field evidence uses that evidence. A property
without field evidence falls back to its parent schema's provenance, preserving
backwards compatibility. Field evidence that is unverified therefore cannot be
hidden by a supported schema-level citation.

The review page can continue to link to `provenance.json`; no new HTML table is
needed because the exact field/property relationship is represented in the
canonical machine-readable provenance artifact.

### Manifest selection (#18)

`manifest --sources <file>` is the supported exact source-selection interface.
It records that file relative to its parent as `sources_root`, leaves scanner
semantics unchanged for directory input, and avoids ambiguous interactions
between a new include glob, default excludes, duplicate detection, and ignored
source reporting. Existing CLI tests and README copy establish this workflow.

The issue will be closed with a comment explaining that an exact file argument
meets the stated use case and is deliberately preferred to an include filter.

## Error handling

- A malformed field source type fails input-schema validation as it does for
  every typed citation field.
- An unresolved citation in a multi-source corpus produces a field-level
  `SOURCE_UNVERIFIED` validation error, with a provenance target that identifies
  the generated property.
- A field with no `source` remains supported only through the parent schema
  citation; this is compatibility behavior, not inferred evidence.

## Tests

Tests cover acceptance of a field `source`, source-guard scope checking,
normalization into typed evidence, direct/nested/array property provenance,
fallback to schema evidence, and fail-closed validation for an unverified
field-level citation. Existing manifest single-file CLI coverage remains the
regression test for #18.

## Scope

This change does not require agents to repeat a schema citation on every field,
does not add source annotations to generated OpenAPI, does not infer evidence
from conventions, and does not introduce `--include` or `--source-file` flags.
