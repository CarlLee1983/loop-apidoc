# loop-apidoc 0.8.0 release notes

Release date: 2026-07-15

## Summary

This minor release makes source-quality assessment results auditable across the
deterministic assembly and Foundry workflows, makes the CI coverage standard
explicit, and adds token-aware agent delivery levels.

## Changed

- `assemble --source-quality <DIR>` accepts the directory produced by
  `assess-sources`.
  - A `reject` verdict stops before a run directory is created.
  - A `pass` verdict preserves `source-quality-report` and `source-diff` artifacts
    under `<run-dir>/source-quality/`, so Foundry imports retain the evidence.
- The quality gate runs the full test suite with coverage and enforces a minimum
  total coverage of 95%.
- CLI, architecture, and release-checklist documentation now describe the current
  source-quality and URL workflow surfaces.
- The `loop-apidoc` skill now tells the user about delivery levels before source
  work begins and asks for `minimal`, `review`, `handoff`, or `full` output.
  `minimal` is the non-interactive default and keeps unselected derived artifacts
  out of agent context and agent-to-agent handoffs, reducing token use.

## Compatibility

- `--source-quality` is optional; existing `assemble` invocations keep their
  existing behavior.
- Output levels are a skill-level delivery and context policy. They do not change
  CLI output contracts, source grounding, or validation.
- No command, output contract, or supported Python version was removed.

## Validation

Run `uv run python scripts/quality_gate.py` before publishing or tagging. The
repository release checklist additionally requires benchmark validation with the
operator-provided local source fixtures.
