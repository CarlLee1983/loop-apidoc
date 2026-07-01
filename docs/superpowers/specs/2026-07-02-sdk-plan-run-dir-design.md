# Design: Single Run SDK Plan Authoring

- **Date:** 2026-07-02
- **Status:** Approved direction, pending spec review
- **Scope:** Use one completed `loop-apidoc` run directory to produce a
  stack-neutral `handoff/sdk-plan.json`.

## Goal

Create the first downstream SDK authoring step without expanding the
`loop-apidoc` core pipeline. The output is a derived SDK planning artifact that
can later feed a language-specific SDK generator or human implementation work,
but it does not choose a programming language and does not generate SDK source
code.

The selected approach is intentionally narrow:

```text
completed run-dir -> loop-sdk-author -> handoff/sdk-plan.json
```

This keeps the current project as the upstream contract source and moves SDK
work into a downstream activity.

## Inputs

The workflow accepts exactly one completed `loop-apidoc` run directory.

Required artifacts:

- `openapi.yaml`
- `integration-contract.json`
- `handoff/sdk-hints.json`
- `validation/report.json` or `validation/report.md`

Optional navigation aid:

- `examples/`

The workflow must not rebuild missing artifacts from Markdown, source PDFs, or
application assumptions. If a required artifact is missing, the SDK plan is not
ready; the gap is reported instead.

## Output

Default output path:

```text
<run-dir>/handoff/sdk-plan.json
```

Required top-level shape follows
`skills/loop-sdk-author/reference/sdk-plan-schema.md`:

- `version`
- `source_run_dir`
- `contracts`
- `runtime.config`
- `operation_groups`
- `operations`
- `mechanisms`
- `adapters`
- `gaps`

The output is a derived handoff artifact, not a new API contract.

## Content Rules

`sdk-plan.json` may contain:

- contract links to `openapi.yaml`, `integration-contract.json`, and
  `handoff/sdk-hints.json`;
- runtime configuration names such as `base_url` and source-stated secrets,
  linked by pointer instead of inlining values;
- operation groups from OpenAPI tags or `sdk-hints.json`;
- operations with `operation_id`, method, path, `sdk_method`,
  `contract_pointer`, `requires`, and `gaps`;
- integration mechanisms with pointers into `integration-contract.json`;
- validation blockers and missing source facts as `gaps`.

`sdk-plan.json` must not contain:

- application framework names or app-stack decisions;
- controllers, routes, middleware, UI components, ORM/database concepts, or
  deployment details;
- copied OpenAPI schemas, request bodies, responses, components, schemas,
  properties, or generated DTO definitions;
- inferred retries, pagination, idempotency, auth defaults, signing behavior, or
  callback semantics.

All API semantics remain in `openapi.yaml` and `integration-contract.json`.
The SDK plan only points to them.

## Data Flow

```text
openapi.yaml
integration-contract.json
handoff/sdk-hints.json
validation/report.*
        |
        v
loop-sdk-author
        |
        v
handoff/sdk-plan.json
        |
        v
validate_sdk_plan.py
```

`handoff/sdk-hints.json` provides grouping and implementation-note hints.
`validation/report.*` supplies known blockers. `examples/` may be referenced as
a navigation aid, but examples are not treated as source.

## Error Handling

- Missing required artifacts become a blocking gap; do not synthesize from other
  files.
- Failed validation reports are carried into `gaps`; do not hide failed
  upstream validation.
- Operations without a stable OpenAPI pointer are invalid for SDK planning.
- Missing source facts stay in `gaps` instead of being filled from SDK
  conventions.

## Verification

The workflow is usable only after this command passes:

```bash
python skills/loop-sdk-author/scripts/validate_sdk_plan.py <run-dir>/handoff/sdk-plan.json
```

Passing validation proves the plan has the required shape and avoids forbidden
framework/schema-copy content. It does not prove any generated SDK compiles,
because code generation is outside this design.

## Non-Goals

- No changes to `loop-apidoc assemble`.
- No Postman work in this phase.
- No multi-run diff or upgrade planning in this phase.
- No generated SDK code.
- No TypeScript, Python, PHP, or other language adapter selection.
- No application framework integration.
- No publishing/package metadata.

## Acceptance Criteria

- Given a completed run directory with the required artifacts, the workflow can
  produce `<run-dir>/handoff/sdk-plan.json`.
- The plan validates with `validate_sdk_plan.py`.
- The plan uses contract pointers instead of copying schema content.
- Validation failures and source gaps are visible in `gaps`.
- The plan remains stack-neutral: `adapters` is empty unless a later, separate
  request explicitly chooses a programming language.

## Next Step

After this spec is reviewed, the implementation plan should define the exact
operational steps for running `loop-sdk-author` against a selected run
directory and validating the generated `sdk-plan.json`.
