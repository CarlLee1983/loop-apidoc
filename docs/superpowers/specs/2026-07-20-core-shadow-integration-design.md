# Core Shadow Integration Design

**Date:** 2026-07-20  
**Status:** Approved for implementation  
**Scope:** Opt-in shadow execution inside the existing `assemble` compatibility adapter

## 1. Goal

Connect the model-independent `domain/` and `core/` foundation to the current
agent-native `assemble` pipeline without changing the existing pipeline's authority.

When explicitly enabled, one assemble run must process the already-verified source and
extraction data through `EvidenceToContractService`, persist the resulting evidence,
claims, canonical contract, policy decision, lifecycle state, events, and a legacy/Core
comparison under `<run-dir>/core/`.

The existing normalization plan, generated artifacts, validation result, run status, and
exit code remain authoritative during this phase.

## 2. Decisions

1. Shadow execution is opt-in through `--architecture-mode shadow`.
2. The default mode is `legacy`; existing callers and outputs remain unchanged.
3. Shadow runs after the legacy validation report has been written, including when legacy
   validation fails.
4. A shadow failure never changes the legacy `RunResult`, validation status, or CLI exit
   code.
5. Shadow execution stops after Core validation. It does not approve, publish, import into
   Foundry, or update a current pointer.
6. Source material remains the only factual authority. Bridge code never supplies missing
   values or inferred conventions.
7. The first evidence granularity is one whole-source fragment per immutable source
   artifact. Finer Markdown-section, PDF-page, and URL-section fragments are future work.

## 3. Non-goals

This change does not:

- make Core policy the production gate;
- replace the mature legacy generators or validators;
- migrate Foundry approval or publication;
- add a persistent production Core store;
- change extraction JSON schemas;
- introduce a new runtime or model call;
- make the reference OpenAPI projection replace `generate/openapi.py`;
- block a run because shadow output is missing, incomplete, or inconsistent.

## 4. Considered Approaches

### 4.1 Inline shadow runner after legacy validation

The existing assemble function passes its in-memory manifest and normalization plan to a
new shadow bridge after legacy generation and validation finish.

**Advantages**

- The source and extraction inputs are parsed only once.
- Every opt-in assemble run produces comparable legacy and Core observations.
- The integration point is narrow and does not wrap or replace the existing pipeline.

**Trade-off**

- `agentcli/assemble.py` becomes aware of one compatibility-sidecar invocation.

**Decision:** selected.

### 4.2 Independent command over a completed run directory

A separate command could load a legacy run and invoke Core afterward.

**Reason rejected for this phase:** a completed run does not retain the original extraction
JSON in its exact input form, so evidence and proposal mapping would be weaker and users
would need to invoke an additional command.

### 4.3 New orchestrator wrapping assemble

A new top-level use case could invoke Core first and treat the complete legacy pipeline as
an adapter.

**Reason rejected for this phase:** this changes a much larger execution boundary and makes
the non-authoritative shadow guarantee harder to prove.

## 5. Architecture

Add a focused `loop_apidoc/shadow/` compatibility package:

| Module | Responsibility |
| --- | --- |
| `models.py` | Architecture mode, bridge diagnostics, comparison, and shadow execution summary values |
| `bridge.py` | Pure conversion from `Manifest` and `NormalizationPlan` into `SourceSet`, `EvidenceBundle`, and `RuntimeResult` |
| `runner.py` | In-memory wiring of `EvidenceToContractService` through Core validation |
| `report.py` | The package's only file-I/O exit; write successful artifacts or a safe error report |

The package is outside Core and Domain because it imports both legacy compatibility types
and the new product contracts. Core and Domain remain unaware of the CLI, run directories,
manifest representation, normalization plan, and shadow mode.

## 6. Execution Flow

The existing assemble sequence remains intact:

```text
load extraction
→ build manifest
→ check extraction
→ build normalization plan
→ generate legacy outputs
→ validate legacy outputs
→ write legacy validation report
```

When `architecture_mode == shadow`, append:

```text
manifest + normalization plan
→ build SourceSet and EvidenceBundle
→ build legacy RuntimeResult containing ClaimProposals
→ EvidenceToContractService.register_source_set
→ acquire
→ request_claim_proposals
→ reconcile
→ build_contract
→ validate
→ compare legacy report with Core decision
→ write <run-dir>/core/*.json
```

Then the unchanged assemble tail persists the legacy run descriptor and returns the legacy
`RunResult`.

The service must use:

- `StaticSourceAdapter` for the deterministic evidence bundle;
- `CallableRuntimeAdapter` for the already-produced legacy proposal result;
- `InMemoryEvidenceStore`;
- `InMemoryContractStore`;
- `InMemoryArtifactSink`, even though publication is not invoked;
- `InMemoryEventSink`;
- `FixedClock(generated_at)`;
- `ApiDomainRulePack` with an explicit version;
- a non-approving placeholder `ApprovalPort`, which is never called.

No system clock, filesystem read, network call, process, browser, or model invocation occurs
inside Core or Domain.

## 7. Source and Evidence Mapping

### 7.1 Source-set identity

The bridge computes a deterministic source-set identity and version from canonical manifest
source metadata. It must not include the runtime identity or a local absolute root path in
the contract identity.

The canonical input is the sorted JSON representation of every source's logical identity,
kind, content digest when present, and usability state. Its SHA-256 digest is used as:

- `SourceSet.id = "source-set-" + digest[:20]`;
- `SourceSet.version = digest`.

Every usable local source becomes a `SourceDescriptor` with:

- `kind="file"`;
- the manifest-relative path as its stable logical locator;
- its recorded media type.

Every URL source becomes a `SourceDescriptor` with:

- `kind="url"`;
- the source URL as its locator;
- no invented media type.

Ignored, duplicate, unreadable, and unsupported local sources do not become evidence
artifacts.

### 7.2 Evidence artifacts

For each usable local source:

- use the manifest SHA-256 as `content_digest`;
- derive a deterministic `SourceArtifact.id` from the digest;
- use the assemble `generated_at` value as `acquired_at`;
- create one `EvidenceFragment` with `locator="whole"` and the same digest.

For a URL source:

- create an artifact only when `content_sha256` is present;
- use the URL as acquisition metadata;
- create one whole-source fragment;
- when `snapshot_file` identifies a local manifest source, allow the URL citation to resolve
  to that local fragment as well.

The bridge never hashes the URL text and presents that hash as a content digest.

### 7.3 Citation resolution

Plan citations resolve by exact `manifest_source` identity:

- local relative path → corresponding local whole-source fragment;
- URL → corresponding URL fragment;
- URL with a snapshot → corresponding URL or local snapshot fragment;
- missing, ambiguous, ignored, unreadable, unsupported, or unacquired source → no evidence
  reference plus a bridge diagnostic.

`query_id` and `answer_path` remain diagnostic lineage and do not substitute for a source
evidence reference.

## 8. Claim-Proposal Mapping

The compatibility bridge maps typed plan entries to proposals. It never copies the plan's
status directly into a Core accepted status; Core reconciliation remains responsible for
status.

| Plan area | `claim_kind` | Subject |
| --- | --- | --- |
| environment | `environment` | environment name or stable plan location |
| endpoint | `operation` | canonical `METHOD path`, or stable plan location when incomplete |
| schema | `schema` | schema name or stable plan location |
| security scheme | `security` | scheme name or stable plan location |
| error | `error` | error code or stable plan location |
| operational entry | `operational_constraint` | topic or stable plan location |
| crypto scheme | `integration_mechanic` | scheme name or stable integration location |
| callback | `webhook` | callback name or stable integration location |
| field condition or contract test | `integration_mechanic` | stable integration location |

Proposal values use only fields present in the typed plan entry. Compatibility conversion
may rename a legacy field into its canonical Domain field, but it may not synthesize a
value.

Status-related behavior:

- `supported`: emit the source-derived value and resolved evidence references.
- `missing`: emit `value=None`; without valid evidence Core will conservatively reconcile it
  as unverified.
- `unverified`: emit the source-derived value without evidence references.
- `conflicting`: emit distinct supported proposals only when distinct source-derived values
  are present. When the legacy plan records a conflict but does not preserve both values,
  emit no fabricated alternative; record a diagnostic and leave the claim unverified.

Duplicate canonical identities remain separate proposals so `reconcile_claims` can merge
matching support or detect genuinely different supported values.

Every proposal ID is a stable SHA-256-derived value over its plan location, claim kind,
subject, predicate, canonical JSON value, and sorted evidence references. It does not
contain the runtime identity.

The bridge uses a fixed compatibility runtime identity and version, recorded in the
`RuntimeResult` and resulting release candidate metadata. Runtime confidence is not set and
does not influence Core policy.

## 9. Contract Metadata

`ContractMetadata` is built deterministically:

- `contract_id = "contract-" + source_set_digest[:20]`;
- `title`: `NormalizationPlan.resolved_title`;
- `version`: `NormalizationPlan.resolved_version`;
- `source_set_id` and `source_set_version`: the bridge-generated values;
- `domain_version`: the explicit shadow Domain version.

`ContractMetadata` currently requires non-null title and version strings. If either value is
absent, the bridge raises a typed shadow metadata error and the safe runner writes
`core/error.json`. It does not substitute `Untitled API`, `unknown`, a filename, a date, or
any other source-silent fallback.

## 10. Core Output Contract

Successful shadow execution writes:

```text
<run-dir>/core/
├── source-set.json
├── evidence.json
├── runtime-result.json
├── claims.json
├── contract.json
├── decision.json
├── workflow.json
├── events.json
└── comparison.json
```

All files use stable UTF-8 JSON with two-space indentation and Pydantic JSON-mode values.
They contain hashes, source identities, locators, values already present in extraction
outputs, lifecycle metadata, and diagnostics. They do not contain raw source bytes.

`comparison.json` contains:

- legacy status;
- legacy error and warning counts;
- sorted legacy issue codes;
- Core verdict;
- sorted Core finding codes;
- `verdict_match`;
- finding codes only in legacy;
- finding codes only in Core;
- counts for supported, missing, conflicting, unverified, waived, and superseded claims;
- bridge diagnostics.

Finding-code comparison is observational. Different taxonomies are expected during shadow
adoption and never alter the legacy result.

`verdict_match` compares blocking semantics, not enum spelling:

```text
legacy report ok == (Core verdict is ACCEPT or REVIEW)
```

Core `REJECT` is the only blocking Core verdict in this comparison.

## 11. Failure Contract

The public shadow entry point catches every shadow-specific exception after the legacy run
directory exists.

On failure it writes:

```text
<run-dir>/core/error.json
```

with:

- `status: "error"`;
- the named shadow stage;
- exception type;
- a safe, single-message description.

It must not include source content, credentials, stack traces, or arbitrary object
representations.

If writing `error.json` also fails, the runner returns an in-memory error summary. The CLI
may print a shadow warning to stderr, but the exception does not escape into the legacy
assemble path.

In every shadow failure case:

- legacy output files remain untouched;
- legacy validation remains authoritative;
- `RunResult.status` is unchanged;
- CLI exit code is unchanged.

Input-boundary failures that happen before a run directory exists remain ordinary legacy
`AssembleInputError` failures; shadow mode does not intercept them.

## 12. CLI Contract

Add:

```text
--architecture-mode legacy|shadow
```

`legacy` is the default.

Direct Python callers of `run_assemble_pipeline` receive a defaulted architecture-mode
parameter, preserving all existing call sites.

When shadow is disabled:

- no `core/` directory is created;
- human-readable output is unchanged;
- JSON output shape is unchanged.

When shadow is enabled:

- human-readable output appends `shadow ok` or `shadow error`;
- `--json` adds a `shadow` object containing status, Core directory, comparison path when
  present, and error path when present.

The `ok` and `status` fields in the existing JSON payload continue to represent legacy
validation only.

## 13. Testing Strategy

### 13.1 Bridge unit tests

Cover:

- stable source-set and artifact identities;
- local and URL evidence mapping;
- URL snapshot mapping;
- excluded and unusable source handling;
- exact citation resolution;
- unresolved citation diagnostics;
- supported, missing, conflicting, and unverified mapping;
- duplicate identity reconciliation;
- deterministic output for identical inputs;
- absence of inferred facts.

### 13.2 Runner tests

Use real in-memory adapters and `EvidenceToContractService` to verify:

- register → acquire → propose → reconcile → build → validate completes;
- approval and publication are never called;
- successful Core artifacts are available to the report layer;
- legacy-pass and legacy-fail inputs both execute;
- a bridge, service, comparison, or report failure is converted to the shadow error
  contract.

### 13.3 Assemble integration tests

Verify:

- default mode creates no Core directory;
- shadow mode writes the complete Core artifact set;
- legacy-failing validation still writes Core artifacts;
- shadow failure preserves the original `RunResult`;
- extraction, source-quality, URL-coverage, and run-directory collision gates retain their
  existing behavior.

### 13.4 CLI tests

Verify:

- accepted architecture-mode values;
- invalid values fail through Typer before assemble;
- default human and JSON output remain byte-for-byte compatible where practical;
- opt-in output includes only the documented shadow additions;
- shadow errors do not change the exit code selected from legacy validation.

### 13.5 Full verification

Run:

```bash
uv run pytest --cov=loop_apidoc
uv run ruff check .
```

Total coverage must remain at or above 95%.

## 14. Documentation and Package-Boundary Updates

Because this adds a user-facing assemble flag and run artifact directory, update the
English-primary and Traditional-Chinese-supporting teaching documents in the same change:

- `README.en.md` and `README.md`;
- `docs/ARCHITECTURE.md`;
- `docs/introduction.en.html` and `docs/introduction.html`;
- `docs/onboarding.en.html` and `docs/onboarding.html`;
- `docs/operator-manual.en.html` and `docs/operator-manual.html`;
- `docs/architecture-manual.en.html` and `docs/architecture-manual.html`;
- `skills/loop-apidoc/reference/assemble-and-correction.md`;
- `AGENTS.md` and `CLAUDE.md`.

Document `shadow/report.py` as a new file-I/O exit. The documentation must state clearly
that shadow artifacts are observational and do not change validation, score, approval,
Foundry, or exit-code behavior.

## 15. Acceptance Criteria

The change is complete when:

1. `assemble --architecture-mode shadow` writes the documented Core artifact set.
2. The default `assemble` behavior and output remain unchanged.
3. Shadow runs for both passing and failing legacy validation results.
4. Any shadow failure produces a non-blocking error summary.
5. No shadow path invokes approval, publication, Foundry, a model, or the network.
6. Unresolved evidence remains unverified and no source-silent fact is created.
7. Core and Domain retain their platform-independent import boundaries.
8. All teaching and agent-guidance documents are synchronized.
9. The full test suite and Ruff pass with at least 95% total coverage.
