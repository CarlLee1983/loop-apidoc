# Run Version Diff Report - Design

**Date:** 2026-06-29
**Status:** Approved for planning
**Topic:** Compare two completed `loop-apidoc` run directories and produce a
human and machine readable change report for downstream implementers.

## Motivation

`loop-apidoc` is positioned as an early material-processing pipeline. Its output
lets the next engineering step start faster by turning uneven source documents
into OpenAPI, integration contract, examples, provenance, and validation
artifacts. That same workflow will repeat whenever upstream API documents are
updated, so maintainers need a deterministic way to answer: what changed between
the previous processed version and the new processed version?

The current pipeline already writes each execution to an isolated run directory:

- `openapi.yaml`
- `api-guide.zh-TW.md`
- `provenance.json`
- `integration-contract.json` when the source states signing, encryption,
  callback, condition, or test-case details
- `validation/report.json` and `validation/report.md`
- `plan/normalization-plan.json`
- generated examples

The missing capability is a run-to-run diff that classifies changes by
downstream impact instead of returning a raw text diff.

## Goals

1. Add a CLI command that compares two completed run directories.
2. Produce both `report.json` and `report.md`.
3. Classify changes into `breaking`, `additive`, `changed`, and `source_only`.
4. Include OpenAPI, integration contract, provenance, and validation status in
   the comparison surface.
5. Keep the implementation deterministic, local, dependency-free, and easy to
   unit test.
6. Avoid speculative semantic-version advice in the first version.

## Non-Goals

- No LLM-based interpretation of changes.
- No external service, database, dashboard, or network access.
- No replacement for `validate`; diff consumes already generated artifacts.
- No extraction-input diff in the first version. Comparing `inventory.json` and
  `endpoints/*.json` is useful for debugging extraction quality, but this
  feature is for comparing deliverable run outputs.
- No automatic migration guide or code generation for downstream SDKs.
- No semver recommendation until impact rules are proven on real runs.

## CLI UX

Add:

```bash
uv run loop-apidoc diff \
  --base output/<old-run> \
  --head output/<new-run>
```

Default output location:

```text
output/<new-run>/diff/
├── report.json
└── report.md
```

Optional output override:

```bash
uv run loop-apidoc diff \
  --base output/<old-run> \
  --head output/<new-run> \
  --output ./diffs/<old-to-new>
```

The command exits:

- `0` when both run directories can be loaded and diff reports are written.
- `2` when a required artifact is missing or malformed.

Diff findings are not validation failures by themselves. A breaking change is a
successful diff result with high impact, not a non-zero process status.

## Change Classes

### Breaking

Changes likely to require downstream implementer action:

- Endpoint operation removed.
- Request method or path removed.
- Required request parameter added.
- Required request property added.
- Existing request parameter or property changes schema type.
- Response schema type changes for an existing status/media type.
- Existing response status is removed.
- Security requirement is removed, renamed, or structurally changed.
- Integration contract crypto/signature/callback rule is removed or changes core
  algorithm, mode, key source, payload assembly, verification field, or expected
  callback response.

### Additive

Changes that expand the contract without invalidating known consumers:

- Endpoint operation added.
- Optional request parameter or property added.
- Response status added.
- Schema property added without becoming required.
- Integration contract item added.

### Changed

Changes that may matter but are not automatically breaking:

- OpenAPI `info.title` or `info.version` changes.
- Server URL or description changes.
- Operation summary or description changes.
- Parameter or property description changes.
- Error code meaning changes.
- Integration contract prose or non-core metadata changes.

### Source Only

Changes that do not alter the machine contract, but affect confidence or
traceability:

- Provenance target citation changes.
- Provenance status changes.
- Validation issue count or issue details change while OpenAPI and integration
  contract remain equivalent.
- Manifest source hashes, URLs, or source availability change.

## Comparison Surface

The first version compares these artifacts:

- `openapi.yaml`: primary API contract surface.
- `integration-contract.json`: signing, encryption, callbacks, field
  conditions, and contract test cases.
- `provenance.json`: source traceability for output targets.
- `validation/report.json`: confidence and known issue changes.
- `manifest.json`: source inventory changes for source-only reporting.

`api-guide.zh-TW.md` is not independently compared in the first version.
Markdown is generated from the same normalized plan and is less stable for
deterministic impact classification, so the main signal should come from
structured artifacts. If structured artifacts are unchanged, a Markdown-only text
change is out of scope for the first version and should be investigated as a
generator determinism issue rather than a contract diff finding.

## Architecture

Add a new package:

```text
loop_apidoc/diff/
├── __init__.py
├── loader.py
├── models.py
├── compare.py
└── report.py
```

### `loader.py`

Loads and validates required artifacts from each run directory:

- YAML parse for `openapi.yaml`.
- Pydantic validation for `provenance.json` using the existing
  `ProvenanceDocument`.
- Pydantic validation for `validation/report.json` using existing
  `ValidationReport`.
- Pydantic validation for `manifest.json` using existing `Manifest`.
- Raw JSON object load for optional `integration-contract.json`.

Malformed required artifacts raise a diff input error before any output is
written.

### `models.py`

Defines the machine-readable report:

```python
class DiffImpact(str, Enum):
    BREAKING = "breaking"
    ADDITIVE = "additive"
    CHANGED = "changed"
    SOURCE_ONLY = "source_only"

class DiffFinding(BaseModel):
    impact: DiffImpact
    area: str
    location: str
    summary: str
    before: Any | None = None
    after: Any | None = None

class DiffReport(BaseModel):
    base_run: str
    head_run: str
    summary: dict[str, int]
    findings: list[DiffFinding] = Field(default_factory=list)
```

The `before` and `after` fields hold compact structured snippets, not whole
artifacts.

### `compare.py`

Owns deterministic comparison logic:

- Build operation keys from `(method.upper(), path)`.
- Compare request parameters by `(in, name)`.
- Compare request and response schemas recursively enough to identify type,
  required, enum, `oneOf`, and `$ref` changes.
- Compare component schemas by component name.
- Compare security schemes and per-operation security arrays.
- Compare integration contract lists by stable best-effort keys:
  - crypto: `name` then `purpose` plus `algorithm`
  - callbacks: `name` then `trigger`
  - field conditions: `scope` plus `when`
  - test cases: `name` then `operation_ref`
- Compare provenance entries by `target`.
- Compare validation issues by `(code, severity, location, evidence)`.
- Compare manifest entries by source path or URL.

Ordering in reports must be stable: impact severity first, then area, then
location, then summary.

### `report.py`

Renders:

- JSON via `DiffReport.model_dump_json(indent=2)`.
- Markdown with counts and grouped findings.

Markdown shape:

```markdown
# Version Diff Report

Base: <path-or-run-id>
Head: <path-or-run-id>

## Summary

| Impact | Count |
| --- | ---: |
| breaking | 1 |
| additive | 3 |
| changed | 2 |
| source_only | 4 |

## Breaking

- `openapi.paths.GET /payments`: response `400` removed
```

## CLI Integration

`loop_apidoc/cli.py` gets a small `diff` command that delegates to the new
package. It should not contain comparison logic.

Pseudo-flow:

1. Load base run.
2. Load head run.
3. Build `DiffReport`.
4. Create output directory.
5. Write `report.json` and `report.md`.
6. Print a terse summary with output path.

## Error Handling

Input errors fail loudly with exit code `2`:

- base or head path does not exist
- required artifact missing
- required artifact cannot be parsed
- required artifact has the wrong schema
- output path points to an existing file

The command may create the output directory only after both inputs are loaded
successfully. This matches the existing assemble behavior of avoiding partial
outputs when inputs are invalid.

## Testing Strategy

Implementation should start with focused tests:

- loader rejects missing or malformed run artifacts.
- endpoint addition is `additive`.
- endpoint removal is `breaking`.
- required request parameter addition is `breaking`.
- optional request property addition is `additive`.
- schema type change is `breaking`.
- response status removal is `breaking`.
- integration crypto algorithm change is `breaking`.
- integration callback detail change is `changed`.
- provenance citation-only change is `source_only`.
- validation issue-only change is `source_only`.
- CLI smoke test writes both `report.json` and `report.md`.

Keep fixtures small and synthetic. The tests should not invoke the full
extraction or assemble pipeline unless a later integration test needs it.

## Acceptance

- `uv run loop-apidoc diff --base <old-run> --head <new-run>` writes
  `diff/report.json` and `diff/report.md` under the head run by default.
- The JSON report uses stable structured models and deterministic ordering.
- The Markdown report is concise enough for maintainers and downstream
  implementers to scan.
- Breaking, additive, changed, and source-only cases are covered by tests.
- Invalid inputs exit `2` without leaving partial output.
- No new dependencies are added.

## Future Extensions

- Add `--format json|markdown|both`.
- Add `--fail-on breaking` for CI gating.
- Add semver recommendation once impact rules are validated on real API update
  cycles.
- Add extraction-input diff for debugging agent parsing changes.
- Add generated examples and Markdown guide diff once the structured contract
  report is stable.
- Add downstream migration notes after enough real findings expose useful
  patterns.
