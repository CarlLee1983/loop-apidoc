# Foundry API Asset Model - Design

**Date:** 2026-07-02
**Status:** Approved for planning
**Topic:** Define a project-local asset model for managing generated API
contract bundles after the current plugin produces them.

## Motivation

`loop-apidoc` currently produces a source-grounded run directory with contract,
review, validation, score, and handoff artifacts. After generation, those
outputs are not managed as reusable project assets. A project may also contain
more than one API document set, so a single project-level "latest output" is not
enough.

Foundry API names the next product concept: raw source documents are forged into
verified, versioned, project-local API contract assets. The current
`loop-apidoc` name remains an implementation-era tool name; Foundry API is the
asset and governance language.

## Goals

1. Define a project-local hidden namespace for Foundry assets.
2. Support multiple API document sets inside one project.
3. Treat each generated run as a candidate that must be promoted before it is
   relied on by downstream workflows.
4. Keep the current plugin output boundary intact: generation writes run
   artifacts; assetization imports or references those artifacts later.
5. Make approved assets discoverable, versioned, and safe to reference from SDK,
   handoff, CI, or integration work.
6. Preserve the existing contract source rule: `openapi.yaml` and
   `integration-contract.json` remain authoritative; helper files remain
   derived aids.

## Non-Goals

- No central hosted registry in the first design.
- No plugin-side asset lifecycle management.
- No automatic approval of every generated run.
- No archival of raw extraction inputs as primary assets in the first design.
- No replacement for `openapi.yaml`, `integration-contract.json`, provenance, or
  validation reports.
- No generated SDK code.

## Naming

The product name is **Foundry API**.

Recommended filesystem namespace:

```text
.foundry/
  api/
```

Rationale:

- `.foundry/` is a project-local asset and governance space, similar in shape to
  `.claude/` or `.codex/`, but not tied to an agent runtime.
- `api/` is broader than `apidoc/`: the managed asset is an API contract bundle,
  not just documentation.
- Foundry gives the product a stable metaphor without forcing every internal
  object to use metaphorical names.

## Vocabulary

| Term | Meaning |
| --- | --- |
| Foundry | Project-local asset governance space under `.foundry/`. |
| Foundry API | The capability that turns source documents into managed API contract assets. |
| Docset | A set of source documents that together form one API contract. |
| Run | One generated output directory from the current plugin / CLI. |
| Candidate | A run imported or referenced for review, but not yet trusted. |
| Asset | A versioned contract bundle registered under a docset. |
| Current | A pointer to the approved asset version that downstream work should use by default. |

## Directory Shape

```text
.foundry/
  api/
    catalog.json
    docsets/
      <docset-id>/
        docset.json
        candidates/
          <run-id>/
        assets/
          <asset-id>/
            asset.json
            artifacts/
              openapi.yaml
              integration-contract.json
              provenance.json
              review.html
              validation/
              score/
              handoff/
        current.json
```

`catalog.json` is the project-level index. It lists docsets and their current
asset pointers, but it does not duplicate every artifact detail.

`docset.json` describes the document set: provider, product, source scope,
source paths or URLs, ownership, and current asset pointer.

`asset.json` describes one asset version: status, run id, source hashes,
validation result, score, artifact paths, supersession link, approval metadata,
and known gaps.

## Docset Model

A docset is not the same as a single source file. It is the unit that answers:
"Which documents together define one API contract?"

Examples:

- One PDF for one provider API -> one docset.
- A primary API PDF plus an error-code markdown file -> one docset.
- Payment, refund, and webhook documents that are released and consumed together
  -> one docset.
- Independent payment and webhook APIs with separate lifecycle ownership -> two
  docsets.

Example `docset.json`:

```json
{
  "docset_id": "tappay-backend",
  "title": "TapPay Backend API",
  "provider": "tappay",
  "product": "backend-api",
  "source_scope": "Payment backend API documents",
  "current_asset": "tappay-backend-20260702-120000",
  "sources": [
    {
      "kind": "file",
      "path": "sources/tappay/backend.md",
      "role": "primary"
    },
    {
      "kind": "file",
      "path": "sources/tappay/errors.md",
      "role": "supplemental"
    }
  ]
}
```

## Asset Model

An asset is a governed contract bundle derived from one plugin run.

Example `asset.json`:

```json
{
  "asset_id": "tappay-backend-20260702-120000",
  "docset_id": "tappay-backend",
  "status": "approved",
  "run_id": "20260702T120000.000000Z",
  "generated_at": "2026-07-02T12:00:00Z",
  "source_hashes": [],
  "validation": {
    "ok": true,
    "score": 92
  },
  "artifacts": {
    "openapi": "artifacts/openapi.yaml",
    "integration_contract": "artifacts/integration-contract.json",
    "provenance": "artifacts/provenance.json",
    "review": "artifacts/review.html",
    "validation": "artifacts/validation/report.json",
    "score": "artifacts/score/score.json",
    "handoff": "artifacts/handoff/"
  },
  "supersedes": null,
  "approved_at": "2026-07-02T12:30:00Z",
  "approved_by": "human-review",
  "known_gaps": []
}
```

## Lifecycle

```text
plugin run output
  -> candidate
  -> approved
  -> selected by current.json
  -> superseded | deprecated
```

States:

| Status | Meaning |
| --- | --- |
| `candidate` | Imported from a run and waiting for review. |
| `approved` | Accepted for downstream use. |
| `superseded` | Replaced by a newer approved asset. |
| `rejected` | Not accepted because validation, score, source, or review failed. |
| `deprecated` | Still available for history, but not recommended for new work. |

Approval should check at least:

- Validation status and score.
- `review.html` scope and source coverage.
- `provenance.json` availability.
- `integration-contract.json` quality when signing, encryption, callbacks, or
  field conditions are present.
- Diff against the previous approved asset when one exists.

## Boundary With Current Plugin

The current plugin remains responsible for generation:

```text
sources -> loop-apidoc / foundry-api generation -> output/<run-id>/
```

Foundry assetization is a separate step:

```text
output/<run-id>/ -> .foundry/api/docsets/<docset-id>/candidates/<run-id>/
candidate -> approved asset -> current pointer
```

This keeps generation deterministic and avoids making every output trusted by
default. A run may be useful evidence without becoming an approved asset.

## Downstream Usage

Downstream workflows should consume approved or current assets, not arbitrary run
directories.

Examples:

- SDK authoring reads `.foundry/api/docsets/<docset-id>/current.json`, then uses
  that asset's `openapi.yaml`, `integration-contract.json`, and
  `handoff/sdk-hints.json`.
- CI contract checks compare a new candidate against the docset's current asset.
- Integration engineers open the approved asset's `review.html`,
  `validation/report.md`, and `handoff/integration-tasks.md`.

## Open Questions

1. Should asset artifacts be copied into `.foundry/`, or should `.foundry/`
   initially store references to immutable run directories?
2. Should `current.json` store only an asset id, or also cache selected asset
   metadata for faster human review?
3. Should approval metadata require a human identity, or allow automated gates
   such as `ci-score-90`?
4. Should the first implementation include a command to import a run into a
   docset, or start with a documented file convention only?

## Acceptance Criteria For Future Implementation

- A project can register multiple docsets under `.foundry/api/docsets/`.
- A docset can hold multiple candidate and approved asset versions.
- Each asset records artifact paths, validation status, score, source identity,
  lifecycle status, and approval metadata.
- Current asset lookup is deterministic for each docset.
- No downstream workflow needs to guess which run directory is trusted.
- The current plugin generation path does not need to own approval or asset
  promotion.
