# Development Opportunities (2026-07-24)

## Scope and conclusion

This inventory excludes downstream delivery/enforcement (roadmap priority 4),
per the current product decision. It also does not reopen the old pipeline
follow-ups: their status marks items 2–7 and the preprocess collision as
delivered, while the diff ledger records its remaining listed fixes as resolved
([`PIPELINE_FOLLOWUPS.md`, lines 6–10 and 255–323](PIPELINE_FOLLOWUPS.md)).

The best next implementation slice is an **operator-facing runtime evaluation
laboratory**. It is independent of unavailable source snapshots and has a clear
public seam. The governance review handoff is the next most valuable workflow
slice. Core production graduation remains strategically important but is not an
honest immediate code-only commitment.

| Priority | Item | Status | User value | Main dependency / risk |
| --- | --- | --- | --- | --- |
| 1 | Runtime evaluation laboratory | Unimplemented operator workflow | Lets operators compare runtimes on reproducible quality, cost, and latency evidence before production use. | Must keep evaluation immutable and unable to mutate/approve production contracts. |
| 2 | Governance review handoff | Partially implemented | Turns a detected source change into an actionable, reproducible human/agent review package. | Must never automatically extract, generate, import, or approve a contract. |
| 3 | Evidence-first review completion | Partial | Reduces review time for field-level changes and makes policy exceptions auditable. | Ambiguous claim mapping and waiver authority need a deliberately designed policy. |
| 4 | Core production graduation | Partial; externally blocked | Eventually removes the legacy/shadow split while preserving deterministic compatibility. | Requires claim-complete, source-backed benchmark parity and historical snapshots. |

## 1. Runtime evaluation laboratory — recommend starting here

**Evidence.** The roadmap explicitly calls for a workflow with versioned cases,
repeatable runtime runs, and reports comparing precision, recall,
support-relationship accuracy, cost, and latency
([`PRODUCT_EXTENSION_ROADMAP.md`, lines 196–206](PRODUCT_EXTENSION_ROADMAP.md)).
The current models already carry versioned cases, relationship metrics, runtime
identity/version, cost, and latency
([`loop_apidoc/evaluation/models.py`, lines 22–67](../loop_apidoc/evaluation/models.py)).
However, the CLI exposes no evaluation command: its command inventory proceeds
from governance through assembly/review, and `evaluation/__init__.py` exports
only `ReplayRunner` (verified from [`cli.py`](../loop_apidoc/cli.py) and
[`evaluation/__init__.py`](../loop_apidoc/evaluation/__init__.py)).

**Recommended seam.** A new `evaluate` CLI command that loads explicitly
versioned immutable cases and runtime-result files, calls the existing replay
API, and writes a JSON/Markdown comparison report. It must not call `assemble`,
Foundry import, or approval.

**TDD acceptance slice.** Given two persisted runtime results for one fixed
case set, emit a deterministic comparison report that includes all roadmap
metrics and marks absent cost/latency as `null`, not guessed. Test the command
and report artifact as public behavior.

## 2. Governance: source change to bounded review handoff

**Evidence.** `governance-scan` already produces a trigger and an immutable
content-addressed snapshot of changed bytes, but the roadmap says the subsequent
human/agent workflow, re-extraction, and approval remain future work
([`PRODUCT_EXTENSION_ROADMAP.md`, lines 120–154](PRODUCT_EXTENSION_ROADMAP.md)).
The command itself writes only the trigger/snapshot
([`loop_apidoc/cli.py`, lines 436–466](../loop_apidoc/cli.py)); the snapshot writer
rejects an existing target directory and atomically writes its evidence pack
([`loop_apidoc/governance/snapshot.py`, lines 17–63](../loop_apidoc/governance/snapshot.py)).

**Recommended seam.** A `governance-review-plan` command taking a governance
trigger/snapshot and producing a review work-item manifest: changed source IDs,
snapshot paths/digests, the current Foundry asset/run reference, and the
required manual steps. It should be a handoff only—no automatic re-extraction
or approval.

**Risk.** Do not collapse the designed authority boundary: change detection
must remain a bounded trigger, not a publisher
([`PRODUCT_EXTENSION_ROADMAP.md`, lines 137–145](PRODUCT_EXTENSION_ROADMAP.md)).

## 3. Evidence-first review: field mapping before waivers

**Evidence.** The review UI already exposes exact evidence for matching
validation findings and unambiguous operation-level HTTP diffs. Field-level and
ambiguous diffs are deliberately unlinked; waivers are explicitly future work
([`PRODUCT_EXTENSION_ROADMAP.md`, lines 168–178](PRODUCT_EXTENSION_ROADMAP.md)).
Core policy has an in-memory, expiry- and scope-aware waiver mechanism
([`loop_apidoc/core/policy.py`, lines 16–78](../loop_apidoc/core/policy.py)),
but this does not demonstrate a review/Foundry persistence or approval flow.

**Recommended seam.** Prefer a deterministic field-diff-to-claim mapping report
first: link only a unique normalized claim target and report every non-unique
candidate as unlinked. This improves navigation without adding authority.

**Follow-on option.** Design persisted, policy-bound, expiring waivers only
after approval semantics are agreed. A waiver may alter review severity, but
must never represent unsupported source material as supported—the roadmap makes
that invariant explicit ([`PRODUCT_EXTENSION_ROADMAP.md`, lines 160–166](PRODUCT_EXTENSION_ROADMAP.md)).

## 4. Core production graduation — prepare, do not promise yet

**Evidence.** The exact-evidence v1 boundary and semantic replay coverage are
delivered, but the roadmap explicitly says this is not Core graduation or
benchmark-parity acceptance
([`PRODUCT_EXTENSION_ROADMAP.md`, lines 77–90](PRODUCT_EXTENSION_ROADMAP.md)).
Only FunkyGames and RSG are reported as full-parity replays; five restored cases
still need claim-complete evidence and six historical snapshots are unavailable
([`PRODUCT_EXTENSION_ROADMAP.md`, lines 100–118](PRODUCT_EXTENSION_ROADMAP.md)).
The benchmark policy requires every material claim to have an exact fragment and
requires every restored snapshot to meet that same bar
([`BENCHMARK_VALIDATION_PLAN.md`, lines 35–52](BENCHMARK_VALIDATION_PLAN.md)).
Correspondingly, code currently offers only `legacy` and non-blocking `shadow`
architecture modes ([`loop_apidoc/shadow/models.py`, lines 28–30](../loop_apidoc/shadow/models.py);
[`loop_apidoc/cli.py`, lines 829–834](../loop_apidoc/cli.py)).

**Recommended next action.** Treat source recovery/permission and
claim-complete evidence for the remaining restored cases as the prerequisite
work. Once the representative gate passes, add a non-default production `core`
mode behind an explicit parity contract. Do not bypass the evidence requirement
with newer, synthetic, or error-page sources.

## Explicitly deferred / excluded

- **Downstream engineering enforcement:** excluded from this inventory because
  it is reported complete by the requester, despite remaining as roadmap text
  ([`PRODUCT_EXTENSION_ROADMAP.md`, lines 180–194](PRODUCT_EXTENSION_ROADMAP.md)).
- **GraphQL/AsyncAPI:** do not begin without real source sets and consumers; the
  roadmap requires a protocol/transport seam in the Canonical IR first
  ([`PRODUCT_EXTENSION_ROADMAP.md`, lines 216–222](PRODUCT_EXTENSION_ROADMAP.md)).
