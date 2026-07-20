# loop-apidoc 0.16.1 release notes

Release date: 2026-07-20

## Summary

Clarify what the benchmark harness proves in CI and locally, and make release
claims accurately distinguish committed, discovered, skipped, passed, and
strict-local-passed cases.

## Changed

- Reworked `docs/BENCHMARK_VALIDATION_PLAN.md` into the canonical,
  English-primary benchmark harness contract, with a supporting Traditional
  Chinese summary.
- Defined the four cumulative harness layers: committed fixture inventory,
  discovery guard, source-backed execution, and strict-local preflight.
- Defined a committed benchmark case by its two identity files and documented
  the exact-parity contract with
  `scripts/quality_gate.py::REQUIRED_BENCHMARK_CASES`.
- Clarified that the harness contains 13 unique case directories, not 13 pytest
  items, because each case feeds several parametrized checks.
- Made the reporting rule explicit: a discovered or skipped case has not passed
  source-backed revalidation, and only a zero-skip strict-local run may be
  described as strict-local passed.
- Documented the historical-source rule: never replace an unavailable dated
  snapshot with a newer document, synthetic fixture, or upstream error page.
- Synchronized the benchmark contract across the English and Traditional
  Chinese READMEs, contributor guide, release checklist, operator manual,
  onboarding guide, and agent guidance.
- Added documentation regression tests for the four-layer terminology,
  canonical links, HTML navigation anchors, and aligned `AGENTS.md` /
  `CLAUDE.md` benchmark sections.
- Made no runtime CLI, extraction, assembly, validation, or artifact-format
  changes.

## Benchmark and source availability

- All 13 committed benchmark cases are discovered and exactly match the
  required inventory.
- Original source snapshots are available locally for
  `funkygames-transfer-operator` and `rsg-game-transfer-wallet`; their
  source-backed assertions execute.
- The remaining 11 operator-provided snapshots are unavailable in this
  workspace. Therefore `quality_gate.py --strict-local` is expected to reject
  the preflight and is not represented as passing.
- A fresh RSG source-backed assemble and structural artifact review covers the
  changed reporting terminology without substituting any historical source.
- The release operator completed the final visual `review.html` inspection
  before tagging.

## 繁體中文摘要

- Benchmark harness 現在明確分成四層：committed fixture inventory、discovery
  guard、source-backed execution、strict-local preflight。
- 13 指的是 13 個唯一 case 目錄，不是 pytest item 數；同一 case 會供多個參數化
  檢查使用。
- 被探索或因缺少來源而 skip 的 case 並未通過 source-backed revalidation；只有全部
  required case 都有原始來源、所有檢查實際執行且零 skip，才能宣稱 strict-local
  passed。
- 本工作區有 FunkyGames 與 RSG 兩組合法來源快照；其餘 11 組缺少
  operator-provided historical snapshots，因此不以新版、合成來源或錯誤頁面代替。
- 本版只修正文件、教學與 release claim 的精確性，不改變 CLI 或產物格式。

## Validation

- `uv sync --dev` — resolved and audited successfully.
- `npm run tag:check` — all existing tags passed the committed SemVer policy.
- `uv run ruff check .` — passed.
- `uv run pytest --cov=loop_apidoc` — 1,206 passed, 81 skipped, 95.20%
  coverage.
- `uv run python scripts/quality_gate.py` — passed Ruff, coverage pytest, and
  6 adversarial CLI smoke scenarios.
- `uv run pytest tests/test_benchmarks.py -ra` — 17 passed and 80 skipped; the
  available FunkyGames and RSG snapshots executed, while assertions requiring
  the 11 unavailable operator-provided snapshots were explicitly skipped.
- `uv run python scripts/quality_gate.py --strict-local` — correctly rejected
  the preflight because those 11 required source snapshots are unavailable;
  strict-local is not represented as passing.
- Fresh RSG shadow assemble — validation passed with 0 errors and 11
  source-faithful warnings, score 93, and shadow status `ok`.
- Fresh RSG structural artifact spot-check — OpenAPI 3.1, 12 request examples
  per language, 123 provenance entries, 3 crypto mechanisms, 15 error codes,
  and all 3 handoff files were present; no placeholder leakage was found.
- `uv build` plus isolated wheel install and CLI smoke — built and installed
  `loop-apidoc 0.16.1` successfully.
- `review.html` visual browser inspection — passed by the release operator.
- `npm run release:tag -- --message "loop-apidoc 0.16.1" --dry-run` — passed;
  would create and push annotated tag `v0.16.1`.
