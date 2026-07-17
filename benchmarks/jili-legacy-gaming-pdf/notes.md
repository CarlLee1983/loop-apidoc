# jili-legacy-gaming-pdf

Legacy JiLi gaming API PDF benchmark. The original PDF, preprocessed Markdown,
and assembled output are intentionally not committed; only the manually verified
extraction metadata is retained.

## Source

- Document: `JiLi 吉利 API 規格書`
- Version: `1.0.52`
- SHA-256: `729c4bb8ff74caf5127376d090231101d81efd6b3321f9ddf47e51f6b94508e6`
- Format: legacy Traditional-Chinese PDF

## Coverage and fidelity decisions

- 20 committed detail files expand to 25 operations. The five FreeSpin routes
  state both GET and POST in the source and are represented by `methods` rather
  than duplicated endpoint records.
- `Key` is an MD5 signing value derived from the UTC-4 date, AgentId, and
  AgentKey. Its construction and a Login example are retained in
  `integration.json`.
- The document provides no concrete API base URL, only `<API URL>` /
  `<API_URL>` placeholders. This is recorded in `inventory.missing` and expected
  as the `servers` completeness warning.
- Endpoint examples are preserved only where source-declared. Missing request or
  response examples deliberately remain completeness warnings, including the
  expanded FreeSpin operations.

## Exclusions

No source PDF, preprocessed source text, generated examples, or assembled
run output is included in this benchmark. Operators may place the original PDF
under `sources/` locally to run the full assemble/validate harness.
