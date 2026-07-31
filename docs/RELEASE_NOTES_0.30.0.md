# loop-apidoc 0.30.0 release notes

Release date: 2026-07-31

## Summary

Add a fail-closed pre-agent source-risk gate and secure provenance-bound DOCX normalization.

## Changed

- Added a deterministic, manifest-bound `inspect-source-risk` gate that runs before any
  agent reads source content, carries its verified audit through source-quality assessment,
  and fails closed when `assemble` sees stale or mismatched source bindings.
- Added bounded DOCX normalization with whole-batch preflight, fail-closed OOXML checks,
  deterministic Markdown and `.source.json` provenance, explicit resource limits, and
  no-overwrite publication. The ZIP/XML fallback is adapted from the pinned, MIT-licensed
  `virgiliojr94/book-to-skill` revision documented in `THIRD_PARTY_NOTICES.md`.
- Split DOCX validation, rendering, models, and publication into explicit pure/I/O boundaries;
  extended regression coverage for unsafe document structures, atomic batch behavior, and
  capped source-risk findings.
- Updated the English and Traditional-Chinese README, landing/introduction pages, onboarding,
  operator and architecture manuals, skill references, design decisions, roadmap, contributor
  guidance, and release checklist. The third-party notice now ships in the wheel.

## Strategy impact

- [ ] None — Not selected because this release updates strategy documents.
- [x] Updated — `docs/DESIGN_DECISIONS.md` records the bounded DOCX adaptation and
  `docs/PRODUCT_EXTENSION_ROADMAP.md` records delivery of the source-risk and secure DOCX
  ingestion slices.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`

The coverage run passed 1,537 tests at 93.85% coverage. It skipped 42 source-backed
benchmark tests because their operator-provided, gitignored source snapshots were not present;
this release does not claim a strict-local benchmark pass.
