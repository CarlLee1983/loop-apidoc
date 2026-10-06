---
status: proposed
---

# Core replaces the legacy path only when every restored benchmark reaches exact-evidence parity

`assemble --architecture-mode` currently offers three execution paths. `legacy` is the
default and the only path most runs take. `shadow` runs the model-independent Core beside
it and is observational only. `strict` is the blocking path: every legacy-supported material
claim must re-verify against exact evidence before it writes an unapproved Core candidate.
`docs/PRODUCT_EXTENSION_ROADMAP.md` (priority 1) states the intent to graduate Core, but
does not say when, or what happens to the two older paths afterwards. Without a recorded
condition, the three modes stay in place indefinitely. Three modes kept forever amount to
a compatibility layer that nobody chose.

This record keeps the question open in a state that can be stored and checked. It does not
answer it.

## Proposed condition

Core graduates when claim-complete exact-evidence parity holds for **all restored
source-backed benchmark cases**. Parity means every material claim is bound to a verified
v1 fragment and the replay is legacy `passed` / Core `accept`. At the time of writing that
holds for 2 of 7 restored cases (FunkyGames and RSG), as reported in the roadmap's
priority-1 progress notes.

When the condition holds, the proposal is:

- `strict` becomes the default `--architecture-mode`;
- `shadow` is removed, because once the blocking path is the default an observation-only
  run has nothing left to observe;
- `legacy` is removed rather than retained as a fallback, following the repository's
  no-compatibility-layer default. Anything that still needs it must be named as an
  external contract before removal.

## Open questions

- **Unavailable historical snapshots.** Six required benchmark cases have no retained
  source snapshot. The roadmap forbids substituting a newer, synthetic, or error-page
  document, so these cases cannot reach parity by recovery alone. The open choice is
  whether graduation waits for them, or whether the cases themselves change. A changed
  case set is itself a decision that needs its own record.
- **Order of removal.** Removing `shadow` before `legacy` would leave no
  observational comparison during the cutover release. The open choice is whether a
  single release removes both.
- **Foundry assets.** Foundry assets imported from `legacy` runs predate strict
  verification. The open choice is whether they need re-verification or only disclosure.

## Consequences

Until this record is accepted or superseded, new work must not extend `shadow` or
`legacy` with behaviour that `strict` lacks. Each such extension raises the cost of the
cutover this record expects.

**Falsified if:** the exit condition stops being the trigger. Concretely, this proposal no
longer describes the system when `loop_apidoc/shadow/models.py`'s `ArchitectureMode` loses
`legacy` or `shadow` while fewer than all restored cases have exact-evidence parity; when
`loop_apidoc/cli.py` changes the `--architecture-mode` default before that parity holds; or
when parity holds for every restored case and both older modes are still present with no
superseding record.
