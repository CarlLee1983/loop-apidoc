# loop-apidoc 0.15.0 release notes

Release date: 2026-07-20

## Summary

Add the opt-in observational Core shadow path and the model-independent evidence-to-contract foundation, while preserving legacy validation authority.

## Changed

- Added the model-independent `domain/`, `core/`, `adapters/`, and `evaluation/`
  foundation. It defines immutable evidence, claim, canonical-contract, policy,
  lifecycle, projection, replay, and governance contracts without depending on
  the current CLI or extraction platform.
- Added opt-in `assemble --architecture-mode shadow`. After the authoritative
  legacy validation report is written, the compatibility bridge runs the same
  source-grounded plan through `EvidenceToContractService` and writes nine
  observational JSON artifacts under `<run-dir>/core/`.
- Kept the default mode at `legacy`. Shadow policy decisions, failures, and
  comparison differences never change legacy validation, score, run status,
  Foundry state, approval, publication, or the CLI exit code.
- Added deterministic source/evidence identities, exact citation resolution,
  structured lineage diagnostics, conservative conflict handling, duplicate-URL
  ambiguity checks, safe error reports, and atomic Core artifact publication.
- Preserved source-silent values as unknown instead of filling Domain defaults.
  Legacy `METHOD /path` references are normalized only into the Domain's
  canonical operation-identity representation.
- Synchronized the English-primary and Traditional-Chinese teaching documents,
  operator manuals, architecture manuals, agent guidance, CLI help, and run-tree
  examples for the new mode and `core/` artifact directory.

## Benchmark

- Re-ran the source-backed `rsg-game-transfer-wallet` benchmark through the new
  CLI shadow path: legacy validation passed with the expected 11 warnings,
  Core returned `accept`, `verdict_match` was `true`, all 33 claims were
  supported, diagnostics were empty, all nine Core files were written, and the
  process exited `0`.

## 繁體中文摘要

- 新增 model-independent 的 Domain／Core／Adapters／Evaluation 基礎，以及選用的
  `assemble --architecture-mode shadow` 觀測旁路。
- 預設 `legacy` 行為不變；Core 結果不會改變既有 validation、score、Foundry、
  approval、status 或退出碼。
- RSG 真實來源 benchmark 已通過：legacy PASS（既有 11 warnings）、Core
  `accept`、33 筆 supported claims、0 diagnostics。

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc` — 1,099 passed, 81 skipped, 95.23% coverage
- `uv run python scripts/quality_gate.py`
- Source-backed RSG shadow benchmark — exit 0, legacy PASS, Core `accept`
