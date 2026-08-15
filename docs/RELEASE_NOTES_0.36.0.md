# loop-apidoc 0.36.0 release notes

Release date: 2026-08-16

## Summary

Make the source-fact gate's no-op visible: SOURCE_FACTS_UNSCANNED

## Changed

- `assemble` now projects, per manifest source, how many source facts were scanned and
  how many of them matched the extraction by endpoint identity (`METHOD /path`), and
  reports the two ways the semantic completeness gate can fail to judge a source as a
  new warning-severity `SOURCE_FACTS_UNSCANNED` validation issue:
  - **zero facts** — nothing was scanned from that source (an HTML source, a flattened
    HTML-to-text dump, or an unconverted PDF/Word file). The remedy is to re-run
    preprocessing along a table-preserving path (`normalize-html-snapshot`,
    `preprocess`), *not* to re-read the source.
  - **zero matches** — facts were scanned but none matched an extracted endpoint. The
    remedy is to check whether the extraction missed the endpoints that source documents.
- The severity is always warning and never changes a run's pass/fail or exit code: a
  legitimate prose-only source with no parameter tables lands in the zero-fact class.
  The issue is scored under source grounding, so two runs of the same product differ in
  score when one had more sources the gate never judged.
- `verify-extraction` forecasts the same projection on stderr before a run directory
  exists, so the preprocessing path can be changed before paying for plan→generate. The
  forecast stays out of `--json` and never changes the exit code.
- The new code is deliberately separate from `SOURCE_UNVERIFIED`: that code's remedy is
  to re-read the source and fill the JSON, which cannot work on a flattened dump.
- Documentation: ADR 0007 records the trade-off; `AGENTS.md` gains a fourth correction
  intent (change the preprocessing path); the skill's assemble/correction reference
  documents the code's severity and routing fields; both operator manuals are synced.

### Benchmark cases that surfaced the warning

Every affected case is the **zero-fact** shape; no case produced the zero-match shape.
The four cases whose sources are machine-readable OpenAPI documents
(`adyen-payments-multimethod`, `apis-guru-baseline`, `funkygames-transfer-operator`,
`stripe-basic-rest`) are unaffected, as expected.

| case | sources newly reported | shape |
|---|---|---|
| `cybersource-payments` | 24 (SDK reference Markdown: `PaymentsApi.md`, `RefundApi.md`, the `Ptsv2*`/`PtsV2*` model pages, `simple-authorizationinternet.md`, …) | zero facts |
| `github-webhooks` | 2 (`webhook-events-and-payloads.md`, `webhook-delivery-and-signing.md`) | zero facts |
| `paypal-webhooks-incomplete` | 2 (`paypal-webhooks-overview.md`, `paypal-webhook-event-names.md`) | zero facts |
| `ecpay-creditcard-pdf` | 1 (`gw_p110.pdf.md`) | zero facts |
| `jili-legacy-gaming-pdf` | 1 (`JiLi_zh-tw.pdf.md`) | zero facts |
| `line-pay-online-v3` | 1 (`online-api-v3-overview.md`) | zero facts |
| `newebpay-mpg` | 1 (`線上交易─幕前支付技術串接手冊_NDNF-1.2.2.pdf.md`) | zero facts |
| `rsg-game-transfer-wallet` | 1 (`rsg-game-transfer-wallet.zh-TW.md`) | zero facts |
| `tappay-backend` | 1 (`tappay-backend-api.md`) | zero facts |

Each case's `expected/validation.expect.json` was updated to the observed counts; the
trigger condition was not narrowed to keep the old expectations. These runs were never
judged by the gate and the reports had said nothing about it — that is the change.

## Strategy impact

- [ ] None — <explain why no strategy document changed>
- [x] Updated — `docs/adr/0007-source-fact-scanning-stays-limited-to-well-structured-markdown.md`

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py --strict-local` (13 cases, zero skips)
