# loop-apidoc 0.31.0 release notes

Release date: 2026-08-02

## Summary

Add governed implementation feedback and exact-scope Effective Contract governance.

## Changed

- Added the `feedback` workflow for deterministic, network-free assessment of passive
  implementation observations against an approved, source-grounded Normative Contract.
- Added eight deterministic feedback routes, semantic operation/response evidence
  allowlisting, bounded open/untested/unresolved counters, and complete-release-digest
  binding for proposals and Effective Contract composition.
- Added governed Foundry persistence for immutable candidate inputs, one non-approval review,
  independent approval, exact-scope/time-bounded Effective releases, supersession lineage,
  stale-artifact detection, and deterministic privacy rejection for sensitive values.
- Added Provider Erratum handoff back into the full source-risk → source-quality → extraction →
  verification → assembly → review → approval pipeline; no empirical observation can mutate
  documentary authority.
- Updated both language versions of the README, landing/introduction, onboarding, operator,
  architecture, roadmap, design-decision, context, contributor, skill, and release-checklist
  documentation, including the accepted authority-separation ADR.

## Strategy impact

- [ ] None — <explain why no strategy document changed>
- [x] Updated — `docs/DESIGN_DECISIONS.md`, `docs/PRODUCT_EXTENSION_ROADMAP.md`, and
  `docs/adr/0002-separate-documentary-and-empirical-authority.md` record the authority split,
  governed feedback workflow, and delivered product-extension scope.

## Validation

- `npm run tag:check`
- `uv sync --dev`
- `npm run docs:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
- `uv run python scripts/quality_gate.py --sanitized-fixtures`

The coverage run passed 1,700 tests at 93.09% coverage. The CI-safe quality gate
passed Ruff, the complete pytest coverage run, and all six adversarial CLI smoke
scenarios. The sanitized-fixture lane passed its exact-evidence replay, Ruff,
pytest, and the same six CLI smoke scenarios. Docsentry and tag policy checks also
passed; no source-backed benchmark claim was made because operator snapshots are
not part of this worktree.
