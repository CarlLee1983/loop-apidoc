# Release Blocker Fixes Design

**Date:** 2026-07-20  
**Status:** Approved for implementation planning

## Context

The 0.16.0 pre-release artifact review found three defects that automated validation did
not catch:

1. request-example renderers treated every explicit CBC scheme as AES, so the RSG
   DES-CBC contract produced incorrect AES code and hex output;
2. `review.html` counted and rendered `plan.schemas`, so an OpenAPI-derived
   `components.schemas.ErrorCode` was absent from the review metric and table;
3. the strict-local preflight listed only ten required benchmark cases even though the
   committed harness contains thirteen.

The fixes must preserve the source-grounding invariant: unsupported or insufficiently
specified cryptography is reported as a gap, never approximated with a conventional
implementation.

## Decision

### Crypto examples: fail closed by supported algorithm

Runnable crypto code and request wiring will require all of the following:

- the scheme is explicit (`algorithm` and `payload_assembly`);
- the mode is confirmed as CBC;
- the algorithm family is AES.

AES-CBC keeps the current runnable Python and TypeScript path. DES-CBC, MD5, GCM, and
other algorithms will emit an algorithm-specific gap function that raises at runtime.
Unsupported schemes must not:

- import AES or `createCipheriv`;
- generate runnable encryption code;
- wire a generated value into a body or header;
- claim that `request.py` or `request.ts` can produce the missing signature.

This release will not add DES runtime support. Correct DES support requires separate
source-backed decisions for key and IV material, padding, output encoding, and Node
runtime compatibility.

### Review page: project the generated OpenAPI

The Schema metric and table will use
`result.openapi.components.schemas`, because the page labels that view as
`components.schemas`.

For schemas that map to `plan.schemas`, the review keeps the plan name, status, and
citations. For OpenAPI-only derived schemas such as `ErrorCode`, the table will:

- show the generated component key;
- use the OpenAPI title when present, otherwise the component key;
- count generated properties and required properties;
- derive status and source references from matching provenance entries.

This keeps the review page aligned with the actual product artifact without duplicating
schema generation logic.

### Strict-local benchmark inventory

`REQUIRED_BENCHMARK_CASES` will include all thirteen committed cases:

- the existing ten cases;
- `jili-legacy-gaming-pdf`;
- `funkygames-transfer-operator`;
- `rsg-game-transfer-wallet`.

A regression test will compare the required tuple with committed benchmark directories
that contain both extraction inventory and validation expectations. A new committed case
will therefore require an intentional quality-gate update instead of silently drifting.

## Error handling

- Unsupported crypto remains a visible generated gap and raises
  `NotImplementedError`/`Error` if called.
- An absent OpenAPI `components.schemas` map renders zero schemas and the existing empty
  table state.
- Missing benchmark source snapshots continue to fail strict-local before expensive
  checks, now with the complete case list.

## Test strategy

Each fix follows red-green TDD:

1. add Python and TypeScript DES-CBC regression tests that require a gap, prohibit AES
   imports/runnable cipher code, and prohibit request wiring;
2. add a review regression test whose plan has errors but no explicit schemas, asserting
   that generated `ErrorCode` appears in both the metric and table with provenance;
3. update the quality-gate required-case test to require exact parity with the thirteen
   committed cases.

After focused tests pass, run:

- `uv run ruff check .`;
- `uv run pytest --cov=loop_apidoc`;
- `uv run python scripts/quality_gate.py`;
- `uv run pytest tests/test_benchmarks.py -ra`;
- a fresh RSG full shadow assemble and artifact assertions;
- package build/install smoke testing;
- `npm run release:tag -- --message "loop-apidoc 0.16.0" --dry-run`.

`quality_gate.py --strict-local` remains expected to fail on machines without all dated,
operator-provided source snapshots. The failure must list every missing required case.

## Documentation impact

Update `docs/RELEASE_NOTES_0.16.0.md` with the fixes and fresh validation counts. Review
English-primary and Traditional-Chinese teaching documents for claims that all crypto
examples are runnable; change only statements made inaccurate by the fail-closed
behavior. No command or CLI flag changes are planned.

## Non-goals

- Implementing DES, MD5, GCM, or a pluggable crypto-renderer registry.
- Changing source extraction or benchmark source snapshots.
- Changing legacy validation authority, Core shadow authority, scoring, or tag creation.
