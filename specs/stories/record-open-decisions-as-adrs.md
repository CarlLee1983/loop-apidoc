# Record the Core graduation and protocol freeze decisions as ADRs

## Goal

Two architecture decisions currently live only as roadmap prose. The first is when the
model-independent Core replaces the legacy path: `--architecture-mode` offers `legacy`,
`shadow`, and `strict`, and `docs/PRODUCT_EXTENSION_ROADMAP.md` reports exact-evidence
parity for only 2 of 7 restored benchmarks. The second is the freeze on GraphQL/AsyncAPI
main-flow integration, last revised on 2026-07-30 in that roadmap's
`## Defer protocol main-flow integration until preceding blockers are resolved`.
Record the first as a `proposed` ADR whose exit condition is checkable. Record the
second as an ADR transcribing the decision already made. Link both from the roadmap and
from the `## 決策邊界` list in `docs/ARCHITECTURE.md`. Undecided work then has a
storable state, and neither decision can be reversed silently.

This Story requires `specs/stories/architecture-adr-boundary-list.md` to be merged
first, because its test requires a boundary row for every ADR.

## Out of Scope

- Changing `--architecture-mode`, removing `legacy` or `shadow`, or changing a default.
- Deciding the Core graduation; ADR 0016 records the question and its exit condition,
  not an answer.
- Deleting, archiving, or rewriting `docs/PIPELINE_FOLLOWUPS.md` or
  `docs/DEVELOPMENT_OPPORTUNITIES_2026-07-24.md`.
- Removing or rewording existing roadmap text; links are only added.
- Existing ADRs 0001-0015.

## Acceptance Criteria

1. Exactly one file matches `docs/adr/0016-*.md`. Its front matter is `status: proposed`.
   Its body names the three modes `legacy`, `shadow`, and `strict`. It states as its exit
   condition that claim-complete exact-evidence parity holds for all restored
   source-backed benchmark cases. Its `**Falsified if:**` paragraph names
   `loop_apidoc/shadow/models.py` and `loop_apidoc/cli.py` in backticks.
2. Exactly one file matches `docs/adr/0017-*.md`. Its front matter is `status: accepted`.
   It cites the 2026-07-30 sequencing decision in `docs/PRODUCT_EXTENSION_ROADMAP.md`.
   It states that no CLI command, run artifact, validation, diff/score, or Foundry path
   for GraphQL/AsyncAPI is added until the ADR records a named downstream consumer and
   its acceptance contract. Its `**Falsified if:**` paragraph names `loop_apidoc/cli.py`
   and `loop_apidoc/domain/projections.py` in backticks.
3. `docs/PRODUCT_EXTENSION_ROADMAP.md` has a relative link to ADR 0016 inside
   `### 1. Make exact evidence first-class, then graduate Core`. It also has a relative
   link to ADR 0017 inside
   `## Defer protocol main-flow integration until preceding blockers are resolved`.
4. `diff <(git show main:docs/PRODUCT_EXTENSION_ROADMAP.md) docs/PRODUCT_EXTENSION_ROADMAP.md | grep '^<'`
   prints nothing.
5. `docs/ARCHITECTURE.md`'s `## 決策邊界` section has rows for ADRs 0016 and 0017
   satisfying `tests/docs/test_adr_boundary_list.py`.
6. `git diff --name-status main...HEAD` lists only `A docs/adr/0016-*.md`,
   `A docs/adr/0017-*.md`, `M docs/PRODUCT_EXTENSION_ROADMAP.md`,
   `M docs/ARCHITECTURE.md`, and this Story file
   (`specs/stories/record-open-decisions-as-adrs.md`).
7. `make verify` exits 0.
