# loop-apidoc 0.33.0 release notes

Release date: 2026-08-10

## Summary

Add a blocking exact-evidence Core candidate path for reviewed Foundry promotion.

## Changed

- Added `assemble --architecture-mode strict`, a blocking Core-candidate path.
  It starts only after legacy validation passes and requires every material claim on
  a legacy-supported plan item to re-verify against exact fragment evidence.
- Strict evidence gaps write `core/grounding-report.json` and fail the run; strict
  execution errors write `core/error.json`, mark the run blocked, and return exit
  code `2`. A successful strict run writes an unapproved `core/release.json` and
  `core/execution.json` with no approval or publication side effect.
- Foundry now fail-closed revalidates declared strict execution, evidence, claims,
  contract, decision, and candidate release bindings before import or human approval.
  `--allow-failing` cannot bypass this boundary.
- Updated the CLI, operator guides, architecture guides, onboarding, and skill
  reference to document strict mode, its output artifacts, and its exit semantics.
- Added Graft navigation and freshness-check guidance, with its local graph cache
  excluded from version control.

## Strategy impact

- [ ] None — <explain why no strategy document changed>
- [x] Updated — `docs/DESIGN_DECISIONS.md` and
  `docs/PRODUCT_EXTENSION_ROADMAP.md` now record the blocking strict candidate
  adapter alongside the observational shadow path and its Foundry governance boundary.

## Validation

- `npm run tag:check`
- `npm run docs:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
- `uv run python scripts/quality_gate.py --sanitized-fixtures`
- `graft check`
