# loop-apidoc 0.32.1 release notes

Release date: 2026-08-08

## Summary

Reduce exact-evidence verification and shadow assembly latency without changing source-grounding semantics.

## Changed

- Exact-evidence verification now builds a single `(source, locator)` lookup instead of
  rescanning the complete fragment bundle for every claim reference. Ambiguous matches,
  stale digests, and missing fragments continue to fail closed.
- The Core shadow bridge now reuses immutable per-run citation and exact-reference indexes,
  eliminating repeated fragment scans and Pydantic equality comparisons while preserving
  evidence ordering and support classification.
- Fragment acquisition now prepares each requested source once: text decoding, line splitting,
  structured JSON/YAML parsing, marked-page parsing, PDF opening, and content hashing are shared
  across requests. Invalid UTF-8 and malformed structured inputs still degrade only the affected
  requests to `UNRESOLVED`.
- The representative FunkyGames shadow-assembly benchmark improved from a median of about 3.47 s
  to 1.40 s (about 60%), while the full test suite improved from 77.77 s to 39.35 s (about 49%)
  on the same development machine.

## Strategy impact

- [x] None — This patch changes internal lookup and source-preparation costs only. Public commands,
  artifacts, source-grounding rules, failure semantics, product direction, and subsystem scope are
  unchanged, so no strategy or teaching document requires a behavioral update.
- [ ] Updated — <list each strategy document changed>

## Validation

- `npm run tag:check`
- `npm run docs:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py --strict-local`
- `uv run python scripts/quality_gate.py --sanitized-fixtures`
