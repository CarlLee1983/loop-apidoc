# loop-apidoc 0.22.2 release notes

Release date: 2026-07-24

## Summary

Stabilize the review command help regression test across supported terminal renderers.

## Changed

- Stabilized the `review --help` regression test across supported Typer/Rich
  terminal renderers. It now verifies the command's successful help response and
  local-candidate-workbench description instead of a renderer-dependent option
  layout.
- This fix-forward release addresses the sole failed assertion in the `0.22.1`
  GitHub Actions run; runtime review behavior is unchanged.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
