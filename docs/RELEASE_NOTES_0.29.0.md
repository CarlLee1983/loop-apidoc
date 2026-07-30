# loop-apidoc 0.29.0 release notes

Release date: 2026-07-30

## Summary

Formalize domain boundaries, strategy governance, sanitized exact-evidence fixtures, and protocol integration freeze criteria.

## Changed

- Reconciled the active product roadmap with the 0.27 and 0.28 deliveries,
  recorded the exact-evidence graduation blockers, and marked the superseded
  2026-07-24 development-opportunities document as a historical snapshot.
- Introduced an optional `PaymentProfile` as the single owner of payment-only
  amount-direction and line-currency semantics. Transport and idempotency remain
  protocol-neutral Core concepts, while legacy 0.27 top-level JSON names remain
  derived read/write compatibility views.
- Added a release-time strategy-governance gate: release notes must declare
  whether strategy changed, and publication fails before external actions when
  that declaration is missing, unresolved, or multiply selected.
- Added the independently reported sanitized-fixture exact-evidence lane, its
  reviewed case inventory, and provenance checks proving that committed subsets
  are line-preserving redactions of available real snapshots. Sanitized results
  remain distinct from source-backed and zero-skip strict-local assurance.
- Kept the deterministic GraphQL and AsyncAPI projection compilers and regression
  seams, while freezing public run integration until a named real downstream
  consumer supplies a source set and acceptance contract.

## Strategy impact

- [ ] None — <explain why no strategy document changed>
- [x] Updated — `docs/PRODUCT_EXTENSION_ROADMAP.md`,
  `docs/DESIGN_DECISIONS.md`, `docs/PROTOCOL_EXPANSION_DESIGN.md`,
  `docs/RESEARCH_PROTOCOL_SOURCE_CANDIDATES.md`, and ADR 0001 now record the
  domain boundary, evidence-lane assurance, roadmap reconciliation, and protocol
  integration freeze.

## Validation

- `npm run tag:check`
- `npm run docs:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
- `uv run python scripts/quality_gate.py --sanitized-fixtures`
