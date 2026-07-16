# loop-apidoc 0.9.3 release notes

Release date: 2026-07-16

## Summary

This patch synchronizes every documentation surface with the 0.9.2 pipeline and
wires the long-existing `--source-quality` gate into the skill's assemble step.

## Changed

- `skills/loop-apidoc/SKILL.md` now passes `--source-quality` to `assemble`
  (the flag existed since 0.8.0 but was never wired into the skill flow: a
  `reject` verdict blocks assembly, a passing report is retained in the
  run-dir's `source-quality/`), and documents static HTML snapshots as a
  supported source type.
- `skills/loop-apidoc/reference/`: `extraction-schemas.md` documents how the
  0.9.2 `x-loop-error-code-map` preserves each error code's meaning,
  HTTP-status metadata, applicability, and citations; `assemble-and-correction.md`
  adds the `source-quality/` run artifact and the exit-2 causes for malformed
  `--url-coverage` / rejected `--source-quality` inputs; `source-quality.md`
  clarifies the two-value verdict (`pass`/`reject`) and the assemble wiring.

## Documentation

- `CLAUDE.md` / `CONTRIBUTING.md`: command surface updated from the retired
  "seven commands" description to the current two groups (14 top-level commands
  plus the `foundry` sub-app); package-boundary and file-I/O maps now cover
  `url_catalog.py`, `url_corpus.py`, `html_snapshot.py`, and `source_quality/`.
- `README.md` / `README.en.md`: added `assess-sources` and `verify-extraction`
  sections, assemble `--url-coverage` and score-loop flags, the
  `x-loop-error-code-map` output description, bilingual section parity, and the
  exact run-id timestamp format.
- `docs/ARCHITECTURE.md`: URL acquisition flow and source-quality gate in the
  diagrams, the 6-key `--json` payload, `loop_verdict`, and the warning-only
  `url_coverage` preparation phase.
- `docs/CORRECTION_LOOP.md`: scope note separating the developer pipeline-fix
  loop from the agent-runtime correction loop.
- HTML manuals (`introduction` / `onboarding` / `operator-manual` /
  `architecture-manual`): fifteen-command coverage, URL navigation/caching and
  quality-gate sections, and current version strings.

## Compatibility

No pipeline code changes; generated artifacts are identical to 0.9.2. The only
behavioral change is in the skill orchestration layer: runs driven by
`SKILL.md` now assess source quality before assembly and fail closed on a
`reject` verdict instead of silently skipping the gate.

## Validation

- `uv sync --dev`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc` (791 passed, 74 skipped; 95.54% coverage)
- `uv run python scripts/quality_gate.py`

## Historical benchmark-source note

Unchanged from 0.9.2: full `--strict-local` revalidation still requires the
operator-provided, dated source snapshots that are absent from this worktree;
they were not replaced with newer documents or error pages.
