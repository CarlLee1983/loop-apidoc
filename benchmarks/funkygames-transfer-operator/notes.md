# funkygames-transfer-operator

## Source

- Official URL: https://funkygames-specs.com/api/swagger/TransferOperator/en/swagger.json
- Downloaded at: 2026-07-17
- Document version: OpenAPI 3.0.4; `info.version` is absent.
- Source format: public machine-readable OpenAPI JSON.
- SHA-256: `d8b0ef20518ea82622754512275e1353f3f3284fc3142771678b7f317debf8da`

## Scope

- Included: all 27 documented operations and all 65 component schemas.
- Excluded: no supplementary documents; this case deliberately verifies a sole JSON-spec source.

## Expected Coverage

- Base URLs: none documented (`servers` is absent).
- Critical endpoints: game list, wallet deposit, and reporting bet list.
- Auth/signing: none documented (`security` and `securitySchemes` are absent).
- Callback/webhook: none.
- Error codes: no standalone error-code catalogue is documented.

## Run Log

- preprocess: not required.
- Source quality: PASS; one immutable JSON snapshot plus URL coverage record.
- Extraction: inventory + 27 endpoint detail files; no `integration.json` because the source states no integration mechanics.
- assemble: initial FAIL exposed that a global `inventory.missing` authentication note was not consumed by the completeness gate. The regression fix now carries that global missing item into the plan, so this fixture passes without an artificial `operational.authentication` workaround.
- validate: OpenAPI 3.1 valid; 0 errors, 28 warnings (27 endpoint examples + 1 operational gap).

## Result

- Status: **PASS**.
- Generated OpenAPI contains 27 paths and 65 schemas, with provenance for each extracted item.
- The source provides neither a server URL nor a security scheme. Both are reported as source gaps; no authentication or host was invented.
- All 28 warnings are faithful: no operation has a source-provided request or response example, and the source has no rate-limit, timeout, or retry information.

## Findings

1. ✅ **[workflow seam fixed] Global `inventory.missing` now reaches agent-native completeness validation.** The case carries `authentication: source does not provide` only in `missing`; the pipeline preserves it as a `MissingItem`, so the gate distinguishes a source-stated absence from an unrecorded omission without a synthetic operational entry.
2. **[machine-readable URL lane]** A direct JSON URL needs an immutable local snapshot and a one-entry coverage ledger, not HTML navigation cataloguing. The source filename in this case is `transfer-operator.swagger.json` and all citations use JSON Pointers beneath it.

## Follow-up

- Source: add provider documentation for base URLs, authentication, and concrete request/response examples before treating generated examples as executable.
