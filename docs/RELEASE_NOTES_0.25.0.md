# loop-apidoc 0.25.0 release notes

Release date: 2026-07-24

## Summary

Add runtime evaluation, bounded governance review handoff, and evidence-first review waivers.

## Changed

- Added `evaluate`, which compares persisted runtime replay results and writes
  immutable quality, cost, and latency comparison reports.
- Added `governance-review-plan`, which turns a verified changed-source snapshot
  into a bounded human/agent review handoff without modifying a contract.
- Extended the Foundry review workbench with exact field-level diff evidence
  mapping and human-approved, expiring waivers. Waivers cannot make insufficient
  or contradictory evidence appear supported.
- Updated the operator, onboarding, architecture, and roadmap documentation for
  the new workflows.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
