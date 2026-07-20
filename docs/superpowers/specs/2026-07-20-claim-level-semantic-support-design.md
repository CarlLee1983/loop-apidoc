# Claim-Level Semantic Evidence Support Design

**Date:** 2026-07-20  
**Status:** Implemented in the opt-in shadow architecture; legacy authority retained
**Scope:** Model-independent Domain/Core contracts and opt-in shadow migration; legacy
generation and validation remain authoritative

## 1. Goal

Upgrade the Evidence Ledger from document-level reference integrity to verifiable,
claim-level semantic support.

For every `GroundedClaim`, Core must be able to answer:

1. Which exact source fragment is involved?
2. Where is that fragment inside the immutable source artifact?
3. Which path inside the claim value does it support or contradict?
4. Which deterministic verifier produced that relationship?
5. Does the set of verified relationships cover every projected leaf of the claim?

An evidence ID that merely exists is not support. A claim becomes `supported` only when
all of its material claim paths have verified `explicit_support` or `derived_support`
relationships to exact, content-bound fragments.

## 2. Current-State Findings

The current implementation has the right architectural seams but not the required
semantics:

- `core.models.EvidenceFragment` contains a string `locator`, but both
  `LocalFileSourceAdapter` and `shadow.bridge` create one `locator="whole"` fragment per
  source.
- The shadow fragment digest is the whole artifact digest. It is not a digest of a cited
  page, section, line range, table cell, JSON value, or HTML node.
- `ClaimProposal.evidence_refs` and `GroundedClaim.evidence_refs` contain fragment IDs
  only. There is no explicit support relationship.
- `core.reconciliation.reconcile_claims` classifies a proposal as valid when its
  `evidence_refs` are non-empty and are a subset of known fragment IDs. It does not compare
  claim content with evidence content.
- `plan.SourceCitation.locator` preserves free-form source text such as `p.2`, but the
  shadow bridge discards the locator and resolves the citation to the source's whole
  fragment.
- `source_facts` already performs conservative deterministic Markdown scanning, but it
  retains only endpoint line numbers, field names, and example counts. It does not retain
  exact table-cell content or fragment identities.
- Legacy `provenance.json` maps an OpenAPI operation or component to a plan citation. It
  cannot distinguish evidence for individual fields inside one operation.
- Core and Domain already have architecture-boundary tests prohibiting platform imports
  and direct system-clock reads. Those tests can be extended instead of introducing a new
  boundary mechanism.

The targeted current baseline passes:

```text
uv run pytest tests/core tests/domain tests/shadow tests/source_facts tests/plan \
  tests/generate/test_provenance.py tests/integration/test_evidence_to_release.py -q
191 passed
```

## 3. Architectural Options

### 3.1 Add typed locators to the existing evidence references

Keep `evidence_refs`, attach a typed locator and excerpt to each referenced fragment, and
continue reconciling by fragment existence.

This improves traceability but not truth conditions. A precise fragment could still be
irrelevant to or contradictory with the claim while Core labels the claim supported.

**Decision:** rejected.

### 3.2 Typed fragments plus a claim-path support graph

Keep the current aggregate claim values, such as an operation definition, but introduce
explicit relationships that bind:

```text
claim identity
+ claim value path
+ exact evidence fragment
+ semantic relationship
+ deterministic verification method
```

Core computes coverage over every material leaf path. A single operation can therefore
use one fragment for its method/path declaration, another for a parameter table cell, and
another for a response status. The aggregate operation is supported only when every leaf
that would enter a projection is covered.

This is additive, preserves the current Canonical API Contract shape, supports field-level
provenance, and gives legacy citations a safe degraded lane.

**Decision:** selected.

### 3.3 Replace aggregate claims with fully atomic field claims

Represent every operation field, parameter property, response property, schema-field
property, and enum member as an independent `GroundedClaim`.

This is semantically elegant, but it requires replacing identity rules, rebuilding the
Domain assembler, migrating all runtimes and evaluation cases, and changing much more than
the shadow seam. It is a possible future evolution after claim-path behavior has production
evidence.

**Decision:** deferred.

## 4. Dependency and I/O Boundaries

The dependency direction remains:

```text
Domain values and pure rules
        ↑
Core reconciliation and use cases
        ↑
Adapters / shadow compatibility / CLI
```

New immutable evidence and support value objects live in
`loop_apidoc/domain/evidence.py`. This permits Domain projection compilers to consume
evidence without importing Core. `loop_apidoc/core/models.py` re-exports the moved evidence
types so existing imports continue to work.

Responsibilities:

| Package | New responsibility |
| --- | --- |
| `domain/evidence.py` | Typed locator, fragment, artifact, support-relationship, and verification enums/value objects |
| `domain/claim_paths.py` | Pure enumeration and lookup of material paths inside canonical claim values |
| `core/verification.py` | Pure deterministic support verification |
| `core/reconciliation.py` | Status decision from verified relationships and path coverage |
| `adapters/fragments.py` | Read source bytes and materialize exact fragments; no decisions about claim status |
| `source_facts/` | Preserve deterministic Markdown endpoint/table-cell facts with exact coordinates and normalized values |
| `shadow/bridge.py` | Convert legacy plan citations and source facts into fragment/support proposals; degrade unresolved legacy citations |
| `domain/projections.py` | Compile OpenAPI/review/provenance trace data from contract plus evidence bundle |

Core and Domain must not import filesystem, network, database, subprocess, browser, CLI,
or model packages. Core receives immutable evidence values and makes no attempt to open a
reconstruction reference itself.

`adapters/fragments.py` becomes an explicit read-side I/O exit. `shadow/report.py` remains
the shadow package's only write-side I/O exit.

## 5. Evidence Contracts

### 5.1 Typed locators

`FragmentLocator` is a Pydantic discriminated union:

```text
WholeDocumentLocator
  kind = "whole_document"

PageLocator
  kind = "page"
  page: int                    # one-based source page

LineRangeLocator
  kind = "line_range"
  start_line: int              # one-based, inclusive
  end_line: int                # one-based, inclusive

SectionLocator
  kind = "section"
  heading_path: tuple[str, ...]
  anchor: str | None

TableLocator
  kind = "table"
  table_index: int             # zero-based within the parent fragment
  heading_path: tuple[str, ...]

TableCellLocator
  kind = "table_cell"
  table_index: int
  row_index: int               # zero-based body row
  column_index: int            # zero-based
  row_key: str | None
  column_name: str | None

JsonPointerLocator
  kind = "json_pointer"
  pointer: str                 # RFC 6901, empty string means document root

CssSelectorLocator
  kind = "css_selector"
  selector: str

XPathLocator
  kind = "xpath"
  expression: str

UnresolvedLocator
  kind = "unresolved"
  raw: str | None
  reason: str
```

The canonical locator representation is canonical JSON using the discriminator and all
non-null fields. Locator equality and IDs do not depend on dict insertion order, local
absolute paths, timestamps, or runtime identity.

Complex locations use fragment parent/child relationships instead of an open-ended
locator object. For example:

```text
PDF page 12
  └── table 1
      └── row 3 / column "Required"
```

### 5.2 Fragment content and digest

`EvidenceFragment` becomes:

```text
EvidenceFragment
  id
  source_artifact_id
  locator: FragmentLocator
  fragment_digest
  normalized_excerpt: str | None
  reconstruction_ref: FragmentReconstructionRef | None
  semantic_value: JSON-compatible value | None
  semantic_role: str | None
  parent_fragment_id: str | None
  precision: exact | document | unresolved
  transformation: tuple[TransformationStep, ...]
```

An `exact` fragment must have at least one of `normalized_excerpt` or
`reconstruction_ref`. A fragment used by a Core verifier must have a materialized
`normalized_excerpt`; a reconstruction-only fragment remains insufficient until an adapter
materializes and rehashes it. Legacy `document` or `unresolved` fragments may omit both
fields so old serialized Core artifacts remain readable, but they can never support a
claim.

Text normalization is deterministic:

1. decode with the source adapter's recorded encoding;
2. normalize Unicode to NFC;
3. normalize line endings to `\n`;
4. remove trailing horizontal whitespace from each line;
5. remove leading and trailing blank lines;
6. preserve case, internal whitespace, punctuation, and line order.

`fragment_digest` is lowercase SHA-256 of the normalized excerpt's UTF-8 bytes. Structured
JSON/YAML values use canonical JSON as the normalized excerpt. A fragment whose supplied
digest does not match its excerpt is never eligible for support.

`EvidenceFragment.id` is derived from:

```text
source_artifact_id
+ canonical locator JSON
+ fragment_digest
+ parent_fragment_id
```

The ID and digest remain stable for identical inputs.

For serialized compatibility, the evidence model accepts the legacy string locator
`"whole"` and normalizes it to `WholeDocumentLocator`. Any other legacy free-form string
normalizes to `UnresolvedLocator`; deserialization must never upgrade an old string to an
exact locator.

### 5.3 Parent/child invariants

Core verifies the evidence bundle before semantic verification:

- every fragment references an existing source artifact;
- every parent references a fragment in the same artifact;
- parent chains are acyclic;
- an `exact` fragment has neither `whole_document` nor `unresolved` locator;
- a materialized excerpt matches `fragment_digest`;
- duplicate fragment IDs must represent identical values.

Whole-document fragments remain valid ledger entries and useful parents. They are not
eligible for semantic support by themselves.

## 6. Claim-to-Evidence Contracts

### 6.1 Runtime proposal

`ClaimProposal` gains:

```text
support_proposals: tuple[ClaimSupportProposal, ...]
```

`ClaimSupportProposal` contains:

```text
fragment_id
claim_path                         # canonical path inside ClaimProposal.value
proposed_relationship              # explicit_support or derived_support
verification_method
derivation_steps[]
runtime_observation: str | None
```

The runtime may point Core at a candidate fragment and verifier. It cannot produce the
authoritative relationship.

`evidence_refs` remains as a deprecated compatibility field during shadow migration.
Core status logic never reads it. Runtime adapters validate the scope of both old
`evidence_refs` and new `support_proposals[].fragment_id`.

### 6.2 Verified relationship

Core produces immutable `ClaimEvidenceRelationship` values:

```text
id
claim_identity
claim_path
fragment_id
relationship:
  explicit_support
  derived_support
  contradicts
  insufficient
verification_method
claim_value_digest
evidence_value_digest: str | None
observed_value: JSON-compatible value | None
reason_code
derivation_steps[]
```

Every relationship points to both a canonical claim identity and a concrete evidence
fragment. Relationship IDs are SHA-256-derived from the canonical relationship payload.

`derived_support` is valid only when every derivation step names a Core-approved,
deterministic transformation and its inputs and output digests validate. A model's prose
reasoning or confidence score is not a derivation.

### 6.3 Claim-path grammar

Claim paths are generated by Domain code, not by runtimes. They are stable semantic paths,
not list-index paths:

```text
/method
/path
/summary
/server
/parameters/{location}/{name}/required
/parameters/{location}/{name}/schema_ref
/responses/{status_code}/description
/responses/{status_code}/schema_ref
/security/{scheme_name}
/fields/{field_name}/type
/fields/{field_name}/required
/fields/{field_name}/condition
```

RFC 6901 escaping is applied to dynamic segments. Domain claim-path helpers enumerate
material leaves and resolve a path back to its value. Lists representing semantic sets are
keyed by stable domain identity instead of source order.

Empty optional collections and absent optional values are not material paths. Values that
would enter OpenAPI, review data, or provenance are material.

## 7. Deterministic Verification

Core initially supports these verification methods:

### 7.1 `exact_normalized_value`

The selected claim value is normalized without lossy coercion:

- strings use text normalization;
- booleans use `true` or `false`;
- numbers use canonical JSON number form;
- objects and arrays use canonical JSON.

Exact equality with a value-bearing fragment produces `explicit_support`. Unequal values
produce `contradicts` only when deterministic structure establishes that the fragment
represents the same semantic role: for example, a table column, JSON Pointer, or
adapter-recorded scalar role. An arbitrary page, section, or line range whose text differs
from a scalar claim produces `insufficient`, not a false contradiction. Missing content, a
broad locator, or an invalid digest also produces `insufficient`.

### 7.2 `table_cell_mapping`

The fragment must have a `TableCellLocator`, a materialized cell excerpt, a column name,
and a deterministic `semantic_value`. Core compares the selected claim leaf with that
value.

The first implementation supports:

- exact field/parameter name mapping;
- exact type string mapping;
- exact enum member mapping;
- requiredness tokens explicitly normalized by a versioned table rule
  (`Y/Yes/true/required/必填/是` and their false counterparts).

Unknown tokens produce `insufficient`, not a guessed boolean.

### 7.3 `structured_field_path`

The fragment must have a `JsonPointerLocator` and a `semantic_value` parsed by the source
adapter. Core compares canonical JSON values exactly. The same verifier handles supported
JSON and YAML/OpenAPI inputs because YAML is converted to a JSON-compatible value by the
adapter and retains its source artifact identity.

### 7.4 `enum_value_comparison`

For an enum-set claim, source and claim sets must be exactly equal after canonical scalar
normalization. For one enum-member claim, the source fragment must contain that exact
member. Partial overlap is `contradicts` for a complete-set claim and `insufficient` when
the proposal explicitly declares an incomplete source fragment.

### 7.5 `source_fact_coverage`

Deterministic Markdown facts may support existence/coverage claims only when the fact
retains an exact fragment:

- endpoint declaration line supports method and path;
- table name cell supports field/parameter existence and name;
- payload fence supports example-presence, not the correctness of the example's semantics.

A count such as `example_blocks=1` without an exact fence fragment is not semantic support.

### 7.6 Verifier selection and model assistance

The runtime proposes a verification method. Core checks that the method is applicable to
the fragment locator and claim path. An incompatible hint produces `insufficient`.

A model may propose:

- a locator;
- a claim path;
- a candidate mapping;
- a derivation;
- a likely contradiction.

The proposal is never truth. Only the deterministic Core verifier creates the final
relationship.

No embedding or fuzzy-similarity score is sufficient by itself.

## 8. Reconciliation Rules

`reconcile_claims` receives claim proposals, an `EvidenceBundle`, and optional previous
claims. It first calls deterministic verification and then reconciles by canonical claim
identity.

For one proposed value:

1. enumerate all material claim paths;
2. collect verified relationships for each path;
3. merge duplicate support for the same normalized value;
4. ignore runtime confidence for status;
5. classify:

| Condition | Claim status |
| --- | --- |
| every material path has `explicit_support` or valid `derived_support`, and no contradiction exists | `supported` |
| any exact fragment contradicts the proposed value | `conflicting` |
| only document-level, unresolved, invalid, inapplicable, or incomplete relationships exist | `unverified` |
| deterministic source representation establishes an explicit missing fact | `missing` |

Across several proposals for one identity:

- fully supported identical values merge relationships and lineage;
- fully supported different values are `conflicting`;
- one supported value plus a contradictory exact fragment is `conflicting`;
- unsupported runtime consensus remains `unverified`;
- an unverified alternative does not override a fully supported value;
- previous identities absent from the new result become `superseded`.

For a conflicting claim, `GroundedClaim.value` contains deterministically sorted distinct
claim/source values and the claim retains both support and contradiction relationships.

`GroundedClaim` gains `support_relationships`. Its deprecated `evidence_refs` is populated
as the sorted distinct fragment IDs from those relationships for read compatibility only.

## 9. Contract Building and Domain Rules

`ContractClaimInput` accepts verified relationships. `EvidenceBinding` becomes an additive
projection-friendly summary:

```text
relationship_id
claim_identity
claim_path
fragment_id
relationship
```

Existing construction with only `fragment_id` remains parseable, but it cannot satisfy the
new `CLAIM_SEMANTIC_SUPPORT_REQUIRED` Domain rule.

The Domain builder:

- includes only `supported` or validly `waived` claims in canonical API objects;
- copies verified relationship bindings to the aggregate object and to the most specific
  child object identified by `claim_path`;
- records insufficient evidence on the `ContractClaim`, but never uses it to project a
  value;
- records contradiction relationships in `Conflict`.

New Domain findings:

- `CLAIM_SEMANTIC_SUPPORT_REQUIRED`;
- `CLAIM_SUPPORT_COVERAGE_INCOMPLETE`;
- `CLAIM_EVIDENCE_CONTRADICTS`;
- `EVIDENCE_FRAGMENT_INVALID`;
- `EVIDENCE_RELATIONSHIP_UNRESOLVED`.

The existing policy engine continues to decide severity. Shadow policy results remain
observational.

## 10. Fragment Acquisition and Source Facts

### 10.1 Adapter behavior

`adapters/fragments.py` materializes fragments outside Core/Domain:

- Markdown: line range, heading section, endpoint declaration, table, table row/cell, and
  fenced payload block;
- preprocessed PDF Markdown: the same plus `<!-- page N -->` page segments;
- native PDF: page fragments through PyMuPDF when a deterministic page locator is present;
- JSON/OpenAPI JSON: RFC 6901 pointer fragments;
- YAML/OpenAPI YAML: pointer fragments over the parsed JSON-compatible tree;
- HTML snapshot: exact selectors only when the snapshot/corpus metadata preserves a
  selector-to-content mapping.

The adapter never converts a free-form citation into support merely because a filename
matches.

Page and section fragments are normally hierarchy/scope nodes. They become semantic
support only through an exact child fragment or a deterministic source-fact mapping. Their
mere presence does not make an unequal scalar value contradictory.

### 10.2 Conservative legacy locator parsing

The shadow compatibility parser recognizes only explicit grammars:

- `p.12`, `page 12`, or `頁 12`;
- `line 10`, `lines 10-14`, or `L10-L14`;
- `§2.1`, an exact Markdown heading path, or an exact `#anchor`;
- RFC 6901 pointers beginning with `#/` or `/`;
- `css:<selector>`;
- `xpath:<expression>`.

Ambiguous prose, missing locators, and unmatched locators become `UnresolvedLocator`.

### 10.3 Source-fact enrichment

`EndpointFact` preserves its current compatibility fields and adds:

- endpoint declaration line range and normalized excerpt;
- section start/end line;
- `TableFact` values;
- `TableCellFact` values with table/row/column coordinates, headers, normalized excerpts,
  and semantic values;
- exact payload-fence fragments.

The scanner stays pure and conservative. `collect_facts` remains the Markdown read-side
exit. A malformed or flattened source still yields no invented facts.

## 11. Shadow Migration

The CLI contract remains:

```text
--architecture-mode legacy   # default, no core/
--architecture-mode shadow   # observational Core sidecar
```

Shadow execution remains after legacy generation and validation.

The revised shadow flow is:

```text
legacy validation report persisted
→ source adapter materializes available exact fragments
→ pure shadow bridge maps plan claims and citations to support proposals
→ Core verifies fragments and relationships
→ Core reconciles claims
→ Domain builds contract
→ Core validates and compiles observational projections
→ shadow report writes core/
```

Legacy citation migration:

| Legacy citation | Shadow result |
| --- | --- |
| exact, materializable locator plus deterministic value match | verified support relationship |
| exact locator whose source value differs | `contradicts`; claim becomes `conflicting` |
| whole document or filename only | `insufficient`; claim remains `unverified` |
| missing or ambiguous locator | unresolved fragment/diagnostic plus `insufficient` |
| model/runtime confidence only | ignored for status |

`evidence_refs` is retained in JSON for compatibility but does not authorize support.

Successful shadow output remains additive under `<run-dir>/core/`:

```text
source-set.json
evidence.json
runtime-result.json
relationships.json          # new
claims.json
contract.json
decision.json
workflow.json
events.json
comparison.json
projections/
  openapi.json               # observational Core projection
  review-data.json           # observational Core projection
  provenance.json            # claim → relationship → fragment → artifact
```

Default legacy runs create none of these files.

Every exception from fragment acquisition, bridge conversion, Core verification,
projection, or report writing is converted to the existing safe shadow error summary.
Shadow success or failure must not alter:

- legacy validation or validation report;
- CLI `ok`, status, or exit code;
- score or score loop;
- approval;
- Foundry import/approval/current pointer;
- run status;
- legacy OpenAPI, review page, provenance, or other artifacts.

## 12. Projection and Provenance

Projection compilers accept a `ProjectionInput` containing the `GroundedApiContract`, its
immutable `SourceSet`, and its `EvidenceBundle`. Calling an existing compiler with only a
contract remains supported for compatibility, but evidence-aware provenance requires the
full input because artifact `source_id` values must resolve to logical source locators.

### 12.1 OpenAPI projection

The observational Core OpenAPI projection adds an `x-loop-claim-map` at the nearest object
that can legally carry an extension. The map connects exact OpenAPI-relative locations to
canonical claim identities and claim paths.

Example:

```json
{
  "x-loop-claim-map": {
    "/summary": {
      "claim_identity": "claim:operation:POST /payments:definition",
      "claim_path": "/summary"
    },
    "/parameters/query/currency/required": {
      "claim_identity": "claim:operation:POST /payments:definition",
      "claim_path": "/parameters/query/currency/required"
    }
  }
}
```

No source excerpt is copied into OpenAPI.

### 12.2 Review projection

The review payload contains:

- contract claims and statuses;
- relationship IDs and kinds;
- claim paths;
- exact fragment locators and digests;
- artifact/source identities;
- verifier and reason codes.

Excerpts remain in `evidence.json` and are joined by fragment ID.

### 12.3 Provenance projection

Each provenance entry is field-specific:

```text
target
claim_identity
claim_path
relationship_id
relationship
verification_method
fragment_id
fragment_locator
fragment_digest
parent_fragment_id
source_artifact_id
source_artifact_digest
source_id
source_locator
```

The chain is therefore:

```text
OpenAPI target
→ claim identity + claim path
→ verified relationship
→ exact fragment
→ immutable source artifact
→ logical source descriptor
```

Different fields inside one operation may resolve to different fragments and source
artifacts.

Legacy `generate/provenance.py` is unchanged in this phase. The richer projection is an
observational Core artifact until a later, separately approved authority migration.

## 13. Compatibility

The migration is additive:

- existing CLI commands and flags are unchanged;
- legacy mode behavior and artifacts are byte-for-byte governed by the existing pipeline;
- `ClaimProposal.evidence_refs`, `GroundedClaim.evidence_refs`, and fragment-ID-only
  `EvidenceBinding` remain parseable but are deprecated;
- existing imports from `loop_apidoc.core.models` continue through re-exports;
- old runtime results remain loadable, but their references produce
  `insufficient/unverified`, never fake support;
- old Core JSON can be read with defaults for new fields;
- Core/shadow JSON gains additive fields/files and an explicit schema version;
- no Foundry or release authority moves to Core.

The compatibility window ends only after evaluation demonstrates that exact-fragment
coverage is adequate and a separate migration approves removing old fields.

## 14. Testing and Acceptance

All implementation follows red/green/refactor TDD. Required tests:

1. a Markdown table cell supports the correct field claim path;
2. a whole-document fragment produces `insufficient` and cannot make a claim supported;
3. a source value different from the claim produces `contradicts` and `conflicting`;
4. several exact fragments supporting the same value merge deterministically;
5. several exact fragments supporting different values produce `conflicting`;
6. fragment digest, canonical locator, fragment ID, relationship ID, and ordering are
   deterministic;
7. parent/child fragment invariants reject missing parents, cross-artifact parents, and
   cycles;
8. runtime confidence never affects claim status;
9. structured JSON Pointer and enum comparison use exact canonical values;
10. different paths in one operation project to different provenance fragments;
11. a legacy citation without a precise materializable locator remains degraded and
    unverified;
12. shadow acquisition/verification/projection/report failures preserve the existing
    legacy result and exit code;
13. default legacy mode still creates no `core/`;
14. Core/Domain architecture tests prohibit filesystem, network, model, subprocess,
    browser, CLI, and database dependencies or direct I/O calls;
15. Ruff passes and total coverage remains at least 95%.

Verification commands:

```bash
uv run pytest tests/domain tests/core tests/adapters tests/source_facts tests/shadow -q
uv run pytest tests/agentcli/test_assemble.py tests/test_cli_assemble.py -q
uv run pytest tests/generate tests/integration tests/evaluation -q
uv run ruff check .
uv run pytest --cov=loop_apidoc
git diff --check
```

## 15. Documentation

Because this changes user-visible shadow behavior and the product architecture, the same
change updates English-primary and Traditional-Chinese-secondary teaching documents:

- `README.en.md` and `README.md`;
- `docs/index.html` and `docs/introduction.html` plus English counterparts where present;
- `docs/onboarding.en.html` and `docs/onboarding.html`;
- `docs/operator-manual.en.html` and `docs/operator-manual.html`;
- `docs/architecture-manual.en.html` and `docs/architecture-manual.html`;
- `docs/ARCHITECTURE.md`;
- `AGENTS.md` and `CLAUDE.md`;
- the loop-apidoc skill references when the extraction citation contract changes.

Documentation must continue to state that shadow is observational and that legacy outputs
remain authoritative.

## 16. Deterministic Verification Limits

The first implementation deliberately leaves these claims unverified unless an exact,
versioned deterministic rule exists:

- paraphrased summaries or descriptions that are semantically similar but not exact;
- multi-paragraph business rules requiring pragmatic or domain interpretation;
- negative claims based only on absence from a source;
- equivalent units or encodings such as `1 minute` versus `60 seconds`;
- merged-cell, image-only, or OCR-uncertain tables whose coordinates/content cannot be
  reconstructed reliably;
- crypto/signature chains that require unstated execution context;
- cross-document conclusions that require selecting one source as authoritative;
- HTML selector claims when the legacy snapshot did not preserve a selector-to-content
  mapping;
- any model-only judgement or embedding-similarity result.

Models may propose candidates for these cases. Core records them as `insufficient` until a
deterministic verifier is added.

## 17. Approval Decisions

Implementation should begin only after the user approves:

1. the selected aggregate-claim plus claim-path support-graph approach;
2. the additive compatibility window for deprecated `evidence_refs`;
3. whole-document legacy citations degrading to `insufficient/unverified`;
4. richer provenance remaining shadow-only in this phase;
5. the deterministic verifier scope and explicit limitations above.
