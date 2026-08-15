# loop-apidoc 0.35.0 release notes

Release date: 2026-08-15

## Summary

Focus directives end-to-end: error-code floor, anchor resolution, and shortfall forecasting

## Changed

- `--focus` focus directives now run end-to-end: an operation, field, or error-code
  anchor is resolved against the extracted inventory, injected into the extraction
  fan-out, and carried through verification into validation.
- Field anchors resolve through schema references, and error-code anchors resolve
  against the typed inventory error catalogue, so a directive can name a code the
  source documents rather than only a literal string.
- A falsified expectation and a not-found answer are now first-class outcomes: a
  not-found answer must account for every readable source, and falsified
  expectations are routed into the validation report instead of being silently
  dropped.
- The run directory gains a focus report describing each directive, its anchor
  resolution, the sources searched, and the outcome.
- A documented error-code floor is derived from source structure alone, with wider
  and hardened recognition of documented codes and the source path carried on each
  fact.
- `verify-extraction` forecasts an error-code shortfall against that floor, with
  structural JSON output and exit-code guarantees.
- Focus directives never enter comparable artifacts (`openapi.yaml`,
  `integration-contract.json`), so runs stay diffable regardless of directives used.
- Documentation: both READMEs document `--focus`; the teaching, promotion, operator,
  onboarding, and architecture manuals are synced in both languages; the promo flow
  demo animation is added.

## Strategy impact

- [ ] None — <explain why no strategy document changed>
- [x] Updated — `docs/DESIGN_DECISIONS.md`, `docs/PRODUCT_EXTENSION_ROADMAP.md`,
  `docs/adr/0004-focus-directives-never-enter-comparable-artifacts.md`,
  `docs/adr/0005-the-error-code-floor-comes-from-source-structure-alone.md`,
  `docs/adr/0006-requiring-exhaustive-error-codes-stays-a-directive.md`

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
