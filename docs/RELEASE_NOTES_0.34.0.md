# loop-apidoc 0.34.0 release notes

Release date: 2026-08-12

## Summary

Require audited source-quality inputs and harden governed Foundry assets.

## Changed

- Made the audited source-quality package a required input to both the public
  `assemble` command and `run_assemble_pipeline`. Assembly now revalidates the
  embedded source-risk audit against the current manifest and source bytes and
  rejects missing, stale, mismatched, or rejected assessments before creating a
  run directory.
- Hardened Foundry's normative asset and current-pointer formats as strict,
  versioned `normative-asset/v1` and `normative-current/v1` records. Governed
  reads now bind the complete artifact manifest, validate every declared digest
  and contained path, require approved lineage, and fail closed on unknown
  fields, symlinks, byte drift, or identity drift.
- Added transaction-pinned staging, per-docset locking, pointer-last
  publication, and ownership-verified rollback for governed Foundry promotion
  and approval paths. Review decisions now bind the complete candidate file set
  before approval.
- Counted OpenAPI specifications discovered while probing SPA shells against
  the shared `cache-url-pages --max-pages` budget. Once the budget is exhausted,
  no further probe request is sent and no extra corpus page is written.
- Stabilized ANSI-sensitive CLI assertions, documented the
  platform-independent coverage denominator, and synchronized the architecture
  documentation with the required assembly inputs and current optional modes.
- Made Markdown source-fact scanning fence-aware, including variable-length
  markers and multi-word info strings. A fenced payload still counts as a
  documented example, while endpoint-like lines and tables inside that fence no
  longer create false endpoint or field completeness requirements.

## Upgrade notes

- Every `assemble` invocation must now pass `--source-quality <assessment-dir>`.
  Create that directory with `assess-sources --source-risk` against the exact
  manifest and source bytes that will be assembled. Reports are rejected when
  stale, internally inconsistent, or changed across a verified manifest,
  source, ruleset, or audit binding.
- Existing unversioned Foundry assets are not read through a compatibility
  fallback. Create a new candidate and use `foundry approve --reapprove-legacy`
  with trusted raw-byte SHA-256 bindings for both the legacy current pointer and
  asset. Preserve the old immutable bytes as migration evidence.
- Treat `--max-pages` as a total corpus-page budget, including a positively
  identified OpenAPI document discovered from an unrendered SPA shell.

## Strategy impact

- [ ] None — Not selected because this release changes mandatory assembly and governed asset boundaries.
- [x] Updated — `docs/DESIGN_DECISIONS.md`, `docs/ARCHITECTURE.md`, and `docs/adr/0003-measure-coverage-on-a-platform-independent-denominator.md` record the updated assurance, governance, and coverage contracts.

## Validation

- `npm run tag:check`
- `npm run docs:check`
- `uv sync --dev`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
- `uv run python scripts/quality_gate.py --sanitized-fixtures`
