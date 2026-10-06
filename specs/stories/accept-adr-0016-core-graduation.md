# Accept ADR 0016 with the owner's answers to its open questions

## Goal

ADR 0016 recorded the Core graduation condition as `proposed` and left three questions
open. The owner has answered all three:

1. The six benchmark cases whose historical snapshots are unavailable do not block
   graduation.
2. One release makes `strict` the default and removes both `legacy` and `shadow`.
3. Foundry assets imported from `legacy` or `shadow` runs stay usable. They are disclosed
   as not Core-verified, and re-verification is not forced.

Record these answers in ADR 0016, mark it `accepted`, and update the two documents that
describe it, so the decision is settled where readers and the boundary test look.
Implementing the cutover is not part of this Story.

## Out of Scope

- Any code change: `ArchitectureMode`, the CLI default, and Foundry disclosure stay as
  they are until parity holds and a separate Story implements the cutover.
- `REQUIRED_BENCHMARK_CASES` and the strict-local gate.
- ADRs other than 0016.
- Roadmap text other than the line that links ADR 0016.

## Acceptance Criteria

1. `sed -n 2p docs/adr/0016-*.md` prints `status: accepted`.
2. ADR 0016 has no `## Open questions` heading. It has a `## Decision` section that
   states each of the three answers in the Goal: the six cases with unavailable
   snapshots do not block graduation and continue to report prerequisites unavailable;
   one release makes `strict` the default and removes `legacy` and `shadow` from
   `ArchitectureMode`; and assets imported from `legacy` or `shadow` runs remain usable,
   are disclosed as not Core-verified, and are not forced through re-verification.
3. ADR 0016's `**Falsified if:**` paragraph keeps its existing conditions and adds three
   more: a case with an unavailable snapshot is made to block graduation without a
   superseding record; a release makes `strict` the default while `legacy` or `shadow`
   remains; and after graduation, Foundry presents a legacy- or shadow-imported asset
   without the disclosure. The paragraph names `loop_apidoc/shadow/models.py`,
   `loop_apidoc/cli.py`, and `loop_apidoc/foundry/strict_artifacts.py` in backticks.
4. The ADR 0016 row in `docs/ARCHITECTURE.md`'s `## 決策邊界` satisfies
   `tests/docs/test_adr_boundary_list.py`.
5. In `docs/PRODUCT_EXTENSION_ROADMAP.md`, the line linking ADR 0016 no longer says
   `proposed`. `diff <(git show main:docs/PRODUCT_EXTENSION_ROADMAP.md) docs/PRODUCT_EXTENSION_ROADMAP.md`
   shows a change to that line only.
6. `git diff --name-status main...HEAD` lists only
   `M docs/adr/0016-core-graduates-when-every-restored-benchmark-reaches-exact-evidence-parity.md`,
   `M docs/ARCHITECTURE.md`, `M docs/PRODUCT_EXTENSION_ROADMAP.md`, and this Story file
   (`specs/stories/accept-adr-0016-core-graduation.md`).
7. `make verify` exits 0.
