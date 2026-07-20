# loop-apidoc 0.16.0 release notes

Release date: 2026-07-20

## Summary

Add deterministic claim-level semantic evidence verification and exact-fragment
provenance to the opt-in Core shadow architecture while preserving legacy authority.

## Changed

- Added typed exact fragment locators for pages, line ranges, sections, tables, table
  cells, JSON Pointers, CSS selectors, and XPath expressions. Fragment identities now bind
  to normalized fragment content instead of treating a whole source as semantic support.
- Added stable material claim paths and deterministic verification for direct values,
  table cells, structured paths, enum values, source facts, and allowlisted derivations.
- Added fail-closed claim/evidence relationships:
  `explicit_support`, `derived_support`, `contradicts`, and `insufficient`.
- Reconciled a claim as `supported` only when every material path is covered by verified
  support. Contradictory evidence or distinct fully supported values produce
  `conflicting`; missing coverage remains unverified.
- Preserved exact support relationships through the Canonical API Contract IR and added
  evidence-aware Core OpenAPI, review-data, and provenance projections.
- Added observational `core/relationships.json` plus
  `core/projections/{openapi,review-data,provenance}.json` artifacts to shadow runs.
- Extended source-fact scanning to retain exact Markdown endpoint, table-cell, and example
  coordinates without widening the conservative extraction gate.
- Kept filename-only, ambiguous, whole-document, reconstruction-only, invalid-digest, and
  unmaterialized legacy citations as `insufficient`/unverified instead of treating
  evidence-ID existence as proof.
- Added semantic-support evaluation metrics and replay expectations without allowing
  evaluation to mutate production state.
- Kept the default architecture mode at `legacy`. Shadow decisions, comparison
  differences, and failures still cannot change legacy validation, score, Foundry state,
  approval, publication, run status, or CLI exit codes.
- Synchronized English-primary and Traditional-Chinese teaching documents, operator and
  architecture manuals, agent guidance, extraction references, and Core artifact trees.

## Benchmark and source availability

- All 13 committed benchmark cases are discovered, including the JiLi legacy PDF case.
- Source snapshots are present for `funkygames-transfer-operator` and
  `rsg-game-transfer-wallet`, so their source-backed assertions run. Operator-provided,
  gitignored snapshots are unavailable for the remaining 11 cases, so
  `quality_gate.py --strict-local` is not represented as passing.
- Deterministic unit/integration coverage, the CI-safe quality gate, and focused
  exact-fragment, verification, reconciliation, shadow-isolation, and projection tests
  cover the changed behavior.
- The release operator must run the strict-local benchmark and manual artifact review when
  the dated source snapshots are available. No substitute document or newer upstream
  revision may be used to manufacture a pass.

## 繁體中文摘要

- Shadow evidence 升級為 claim-level semantic support，以 exact typed fragment、
  material claim path 與 deterministic relationship 建立可驗證追蹤鏈。
- 只有所有 material paths 都獲得支援時，claim 才會成為 `supported`；矛盾證據會
  產生 `conflicting`，整份文件、無法解析或僅檔名的 legacy citation 維持
  `insufficient`／unverified。
- 新增 `core/relationships.json` 與 evidence-aware OpenAPI、review-data、
  provenance projections；legacy pipeline 仍是 validation、score、Foundry、
  approval、status 與退出碼的唯一權威。
- 本工作區有 2 組 source-backed benchmark 可執行，另 11 組缺少
  operator-provided sources；正式發版前仍需由 release operator 執行完整
  strict-local benchmark 與人工 artifact spot-check，不以替代文件製造通過結果。

## Validation

- `uv sync --dev` — resolved and audited successfully.
- `npm run tag:check` — all existing release tags passed the committed SemVer policy.
- `uv run ruff check .` — passed.
- `uv run pytest --cov=loop_apidoc` — 1,193 passed, 81 skipped, 95.21% coverage.
- `uv run python scripts/quality_gate.py` — passed Ruff, coverage pytest, and 6
  adversarial CLI smoke scenarios.
- Focused release/semantic-evidence matrix — 129 passed.
- Benchmark harness — 13 cases discovered; 2 source-backed cases executed, 17 checks
  passed, and 80 checks skipped because the remaining operator-provided snapshots were
  unavailable.
