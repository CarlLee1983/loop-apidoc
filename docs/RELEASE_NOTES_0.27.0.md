# loop-apidoc 0.27.0 release notes

Release date: 2026-07-28

## Summary

Add source-grounded typed integration semantics and stronger contract quality
signals.

## Changed

- Added optional typed `integration.json` collections for transport policy,
  amount direction, idempotency, and line-currency policy. Operation references
  are checked against the extracted endpoint inventory, and source evidence is
  projected through the canonical Domain contract, shadow relationships,
  provenance, the Traditional-Chinese guide, and the always-written
  `integration-contract.json`.
- Kept the source-only invariant explicit for wallet and payment semantics: a
  missing request currency field is not evidence of a single-currency line, and
  an unstated policy remains `null` with the gap recorded in `missing`.
- Added validated `operational[].applies_to[]` references so cross-endpoint rules
  can target an operation or field without relying on downstream interpretation.
- Added warning-level coverage findings for readable sources with no material
  citations and for successful responses with no usable schema fields. Response
  operation, field, and hollow-response metrics are also exposed in score
  reports without changing validation pass/fail semantics.
- Updated the loop-apidoc and loop-sdk-author skills, schemas, handoff guidance,
  architecture references, and English/Traditional-Chinese teaching surfaces
  for the new contracts and quality signals.
- Existing extraction files remain compatible: all new typed collections and
  applicability references are optional and additive.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
