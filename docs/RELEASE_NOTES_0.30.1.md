# loop-apidoc 0.30.1 release notes

Release date: 2026-08-01

## Summary

Harden source verification and immutable publication while improving the introduction and onboarding experience.

## Changed

- Reject conflicting evidence identities, dangling references, duplicate protocol operations,
  invalid component names, and projections that would silently lose request schemas.
- Protect DOCX normalization, rendered-URL import, and OpenAPI snapshot publication from
  overlapping destinations, dangling symlinks, write races, and unsafe rollback behavior.
- Align the benchmark expectations and operator notes with source-backed validation results;
  the intentionally incomplete PayPal webhook case remains an expected failure.
- Improve the English and Traditional-Chinese introduction and onboarding pages with clearer
  learning paths, reading progress, responsive navigation, accessibility, and mobile layout.

## Strategy impact

- [x] None — This patch hardens existing validation and publication boundaries and refines existing teaching pages without changing product direction, roadmap priority, or subsystem scope.
- [ ] Updated — Not selected because no strategy document changed.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`

The coverage run passed 1,619 tests with no skips at 94.05% coverage. The CI-safe
quality gate also passed Ruff, the complete pytest coverage run, and all six
adversarial CLI smoke scenarios.
