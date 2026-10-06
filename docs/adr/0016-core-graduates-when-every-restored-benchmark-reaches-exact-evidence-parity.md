---
status: accepted
---

# Core replaces the legacy path only when every restored benchmark reaches exact-evidence parity

`assemble --architecture-mode` currently offers three execution paths. `legacy` is the
default and the only path most runs take. `shadow` runs the model-independent Core beside
it and is observational only. `strict` is the blocking path: every legacy-supported material
claim must re-verify against exact evidence before it writes an unapproved Core candidate.
`docs/PRODUCT_EXTENSION_ROADMAP.md` (priority 1) states the intent to graduate Core, but
did not say when, or what happens to the two older paths afterwards. Without a recorded
condition, the three modes would stay in place indefinitely. Three modes kept forever
amount to a compatibility layer that nobody chose.

This record was first written as `proposed` with three open questions. The repository
owner has answered them, and the answers are recorded below.

## Condition

Core graduates when claim-complete exact-evidence parity holds for **all restored
source-backed benchmark cases**. Parity means every material claim is bound to a verified
v1 fragment and the replay is legacy `passed` / Core `accept`. At the time of writing that
holds for 2 of 7 restored cases (FunkyGames and RSG), as reported in the roadmap's
priority-1 progress notes.

## Decision

- **Unavailable historical snapshots do not block graduation.** Six required benchmark
  cases have no retained source snapshot. The roadmap forbids substituting a newer,
  synthetic, or error-page document, so recovery alone may never bring them back. Waiting
  for them would keep the three modes indefinitely, which is the outcome this record exists
  to prevent. These cases continue to report prerequisites unavailable, and nothing about
  them is lowered or replaced. Changing the required case set would be a separate decision
  with its own record.
- **One release makes `strict` the default and removes `legacy` and `shadow` from
  `ArchitectureMode`.** `strict` already re-verifies every legacy-supported material claim,
  so it carries its own comparison, and an observation-only `shadow` run has nothing left to
  observe. Keeping `legacy` for a release as a fallback would be the compatibility layer this
  repository declines by default. Anything that still needs it must be named as an external
  contract before the release.
- **Foundry assets imported from `legacy` or `shadow` runs are disclosed, not re-verified.**
  Those assets predate strict verification. Re-verification would need the sources as they
  were at import time, and those sources are not guaranteed to be available. Forcing it
  would strand assets for a reason that has nothing to do with whether they are correct.
  After graduation the assets remain usable, and Foundry marks them as not Core-verified
  wherever it presents them.

## Consequences

Until parity holds, new work must not extend `shadow` or `legacy` with behaviour that
`strict` lacks. Each such extension raises the cost of the cutover. The cutover release
must also add the Foundry disclosure; removing the modes without it would leave
legacy-imported assets indistinguishable from verified ones.

**Falsified if:** the exit condition stops being the trigger, or the cutover departs from the
answers above. Concretely, this decision no longer describes the system when
`loop_apidoc/shadow/models.py`'s `ArchitectureMode` loses `legacy` or `shadow` while fewer
than all restored cases have exact-evidence parity; when `loop_apidoc/commands/extraction.py` changes the
`--architecture-mode` default before that parity holds; when parity holds for every restored
case and both older modes are still present with no superseding record; when a case with an
unavailable snapshot is made to block graduation without a superseding record; when a release
makes `strict` the default while `legacy` or `shadow` remains; or when, after graduation,
Foundry presents an asset imported from a `legacy` or `shadow` run without the not
Core-verified disclosure, which today would mean `loop_apidoc/foundry/strict_artifacts.py`
still lets such runs through its established path silently.
