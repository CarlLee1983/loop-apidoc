# Local Review Workbench Design

**Date:** 2026-07-23
**Status:** Approved for implementation
**Topic:** A local, single-user GUI for reviewing a Foundry candidate against the
current API-contract asset, recording a structured handoff, and explicitly
promoting the candidate.

## Motivation

The pipeline already turns PDF, HTML, Swagger/OpenAPI, and other supported
source formats into comparable run artifacts. `loop-apidoc diff` classifies
contract changes deterministically and Foundry stores candidate and approved
assets. What is missing is an operator surface between those two capabilities:
an operator needs to see the candidate, current asset, validation, provenance,
and diff together; record what still needs work; then decide whether the
candidate should become `current`.

The workbench serves a single local project. It is not a hosted product,
multi-user collaboration system, identity system, model runtime, or replacement
for the source-grounded pipeline.

## Goals

1. Start a loopback-only review GUI through `loop-apidoc review`.
2. Accept one completed run, validate it, and import it as a Foundry candidate
   without a separate manual `foundry import` command.
3. Compare the candidate with the docset's current asset in memory; present a
   baseline review when no current asset exists.
4. Let the human record per-item dispositions and structured follow-up work for
   existing tools or AI agents to consume later.
5. Let that same human explicitly approve the candidate from the GUI.
6. Allow approval with validation failures, high-impact changes, or unresolved
   follow-up work, while making that risk unmissable to downstream tools.
7. Keep every generated contract, validation report, provenance record, and
   deterministic diff result immutable from the workbench's perspective.

## Non-goals

- No accounts, reviewers, login, audit identity, multi-user editing, or hosted
  service.
- No model selection, model invocation, automatic correction, or automatic
  approval.
- No new semantic diff classifier. The existing `diff` comparison remains the
  authority for contract-impact classification.
- No mutation of `openapi.yaml`, `integration-contract.json`,
  `provenance.json`, `validation/`, or generated `review.html`.
- No arbitrary filesystem browser or arbitrary local command execution from the
  browser.

## Vocabulary

| Term | Meaning |
| --- | --- |
| Review workbench | The local GUI plus its workflow service. |
| Candidate | A Foundry-imported completed run awaiting or receiving review. |
| Baseline review | Review of a candidate when a docset has no current asset; it has no diff. |
| Review decision | The structured human record attached to one candidate. |
| Handoff | Open, machine-readable follow-up work derived from the human decision. |
| Review state | Readiness signal on an approved asset/current pointer: `reviewed`, `needs_follow_up`, or legacy `unreviewed`. |
| Binding | Identity and digest data that ties a decision to the exact candidate, base, and in-memory diff it reviewed. |

`reviewed` does not make a contract a new source of truth. It means a human
reviewed the generated candidate. The original supplier documents remain the
only source authority.

## User flow

```text
completed run
  -> loop-apidoc review --project <project> --docset <docset> --run <run>
  -> validate run and import/reopen candidate
  -> load current asset, or enter baseline mode
  -> deterministic in-memory diff (when current exists)
  -> local GUI: inspect, save decision and handoff
  -> human presses approve
  -> Foundry copies candidate to an asset and updates current
```

The `--run` invocation is idempotent only when an existing candidate with the
same run ID has the same canonical artifact digests. In that case it reopens the
candidate and retains its review decision. A differing candidate with the same
run ID is an input collision and fails without overwriting evidence.

The command starts a server on `127.0.0.1` with an ephemeral port by default,
opens the URL in the default browser, and prints the URL. A browser-launch
failure is non-fatal. `--port` and `--no-open` support deterministic testing and
manual browser launch.

## Review workflow module

Add `loop_apidoc/review/` as the deep module and test seam. The CLI and local
web adapter must not coordinate Foundry, diff, bindings, and persistence on
their own. Its public operations are:

```python
open_review(request: ReviewRequest) -> ReviewSnapshot
save_decision(key: ReviewKey, draft: ReviewDraft) -> ReviewSnapshot
approve_review(key: ReviewKey, draft: ReviewDraft, *, now: datetime) -> ApprovalResult
```

`open_review` validates/imports or reopens the candidate, resolves the current
asset, loads candidate/base artifacts, creates an in-memory `DiffReport` when
applicable, and builds a binding. `save_decision` validates the binding and
persists the review sidecar. `approve_review` rechecks the binding, saves the
decision, derives review state and known gaps, then calls Foundry promotion.

The workflow may compose the existing Foundry importer, store, query, and
approval functions plus `diff.loader` and `diff.compare`; no generic repository
or model adapter is justified for this one local implementation.

## Decision and handoff data

The decision is stored at:

```text
.foundry/api/docsets/<docset>/candidates/<run>/review/decision.json
```

It is governance data, not a generated run artifact and not the existing
`handoff/` directory. Foundry's existing copy-on-approve behavior carries it
into the approved asset as `artifacts/review/decision.json`.

The minimum schema is versioned and contains:

```json
{
  "schema_version": 1,
  "binding": {
    "docset_id": "provider-payments",
    "candidate_run_id": "20260723T120000.000000Z",
    "candidate_artifact_digests": {"openapi.yaml": "..."},
    "base_asset_id": "provider-payments-20260720-120000",
    "base_artifact_digests": {"openapi.yaml": "..."},
    "diff_digest": "..."
  },
  "items": [
    {
      "subject_id": "sha256:...",
      "subject_kind": "diff",
      "disposition": "needs_evidence",
      "note": "Confirm the authentication header from the supplier source.",
      "requested_action": "recheck_source"
    }
  ],
  "handoff": [
    {
      "task_id": "auth-header-evidence",
      "status": "open",
      "instruction": "Re-read the supplier authentication section and cite the header.",
      "subject_ids": ["sha256:..."]
    }
  ],
  "saved_at": "2026-07-23T12:00:00+00:00"
}
```

Subject IDs are deterministic SHA-256 references of canonical JSON for a diff
finding or validation issue. They do not duplicate whole source or contract
content. Manual items are permitted when no existing finding captures the work.

The binding includes digests for `openapi.yaml`, `provenance.json`,
`validation/report.json`, `manifest.json`, and any present integration or
preparation artifact. It prevents an old decision from approving altered
candidate or base evidence. Saving or approving a stale binding fails and
requires reopening the workbench.

## Foundry model changes

Retain `AssetStatus.APPROVED`; follow-up is review readiness, not a lifecycle
rejection. Add a `ReviewSummary` to `Asset` and `CurrentPointer`:

```text
state: unreviewed | reviewed | needs_follow_up
decision_path: optional relative artifact path
open_handoff_count: non-negative integer
```

Existing assets load as `unreviewed` for compatibility. GUI approval sets
`reviewed` only when validation passes and all required review items and handoff
tasks are resolved. Otherwise it sets `needs_follow_up`. `known_gaps` remains a
compatible flattened summary of unresolved work.

GUI approval does not record a reviewer identity. `Asset.approved_by` is already
nullable; make the Foundry approval function accept `None`. The existing
`foundry approve --by` command may retain its explicit option for compatibility.

Approval still requires a valid, saved decision. That is a process-integrity
requirement, not a content gate: validation failures, low scores, unaddressed
diffs, or unresolved handoff work may be promoted and are reflected in
`needs_follow_up`.

## Local web adapter

The web adapter is thin and delegates all business behavior to the review
workflow. Use the Python standard library rather than introducing a web
framework. It serves bundled static HTML/JavaScript and a small fixed route
set:

- `GET /api/review` returns a review snapshot.
- `PUT /api/decision` saves a decision.
- `POST /api/approve` promotes the candidate.
- Fixed read-only artifact routes serve only approved candidate/base artifacts
  selected by the snapshot.

The server binds only `127.0.0.1`, requires an unguessable per-session token
for writes, rejects path traversal, and revalidates every write request. It
never executes an AI agent or exposes arbitrary project files. The generated
run `review.html` remains an immutable linked artifact, not a writable form.

## Error behavior

Hard errors are identity or integrity failures: unknown docset, malformed run,
corrupt candidate/current asset, different content at an existing candidate ID,
invalid decision schema, unknown subject ID, stale binding, or Foundry write
failure. The CLI reports input failures as exit `2`; the web adapter reports
stale binding as `409` and invalid decisions as `422`.

Approval failures must leave `current.json` unchanged. A current pointer that
exists but cannot be loaded is an error, never a reason to silently use
baseline mode.

## Documentation and tests

This feature intentionally supersedes only the old version-diff design's
dashboard non-goal: the deterministic `diff` module remains headless and
unchanged in responsibility; the new local workbench consumes it in memory.

Tests must cross the workflow seam for automatic import/reopen, baseline versus
comparison, decision persistence, digest staleness, soft approval,
`needs_follow_up`, candidate-to-asset copying, and legacy model defaults. A
narrow adapter test covers loopback binding, fixed routes, session-token write
protection, and path-traversal rejection. Existing Foundry, diff, and generated
review-page tests remain authoritative regression coverage.

Update CLI help, both READMEs, the operator/onboarding/architecture manuals,
the introduction pages, and `AGENTS.md`/`CLAUDE.md` for the new user-visible
command and governance behavior.
