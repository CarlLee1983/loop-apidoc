---
name: loop-sdk-author
description: Use when converting a loop-apidoc run directory, openapi.yaml, integration-contract.json, handoff/sdk-hints.json, or examples into a stack-neutral SDK authoring plan or SDK guidance without choosing an application framework or app tech stack.
---

# Loop SDK Author

## Overview

Create SDK authoring plans from verified `loop-apidoc` outputs. The SDK may be
prepared before the consuming application exists, but the application framework,
product flow, persistence layer, UI, and deployment stack remain out of scope.

## Inputs

Use only these contract artifacts from a completed run directory:

- `openapi.yaml` for operations, parameters, schemas, security, servers, and tags.
- `integration-contract.json` for signing, encryption, callbacks, field
  conditions, and contract tests.
- `handoff/sdk-hints.json` for operation grouping, implementation order, gaps,
  and contract pointers.
- `examples/` only as derived navigation aid; do not treat examples as source.

If any required artifact is missing, report the gap instead of rebuilding it from
Markdown or app assumptions.

## Workflow

1. Read `reference/sdk-plan-schema.md` before drafting a plan.
2. Inspect `validation/report.json` or `validation/report.md`; if the run failed,
   carry blockers into the SDK plan and do not hide them.
3. Draft a stack-neutral `sdk-plan.json`. Default location when writing a derived
   sidecar is `<run-dir>/handoff/sdk-plan.json`.
4. Run `python skills/loop-sdk-author/scripts/validate_sdk_plan.py <sdk-plan.json>`.
5. Fix validator failures before presenting the plan as usable.
6. Generate target-language SDK code only after the neutral plan passes. Keep the
   code language-level, not framework-level.

## Boundaries

- Do not select or mention an app stack such as React, Next.js, Vue, Angular,
  Django, FastAPI, Laravel, Rails, Spring Boot, or similar frameworks.
- Do not create controllers, UI components, routes, database models, ORMs,
  middleware, or deployment files.
- Do not copy OpenAPI schemas into the SDK plan. Use `contract_pointer` values
  back to `openapi.yaml`.
- Do not infer retries, pagination, idempotency, authentication defaults,
  signing details, callback behavior, or error semantics from convention.
- Source-missing values become `gaps`; they are not filled from typical SDK
  practice.

## Plan Shape

The plan is a portable contract for later SDK generation:

- `runtime.config` lists configurable values such as `base_url` and secrets.
- `operation_groups` mirrors OpenAPI tags or `sdk-hints.json` groups.
- `operations` lists SDK method names and `contract_pointer` links only.
- `mechanisms` links auth, crypto, callbacks, and tests back to
  `integration-contract.json`.
- `adapters` is empty unless the user asks for a specific programming language.
  Language adapters may name a language package layout, but not an application
  framework.

## Pressure Rules

| Temptation | Required response |
| --- | --- |
| "A framework example would make this easier to use." | Keep it out of the SDK plan; create only language-neutral SDK guidance. |
| "The OpenAPI schema is available, so copy properties into the plan." | Use JSON pointers to `openapi.yaml`; do not duplicate schema. |
| "SDKs usually retry or paginate this way." | Add a gap unless the source states it. |
| "The user probably wants a web app integration." | Stop at SDK boundaries unless the user explicitly scopes a separate app task. |

## Validation

Always run the validator before claiming the SDK plan is ready:

```bash
python skills/loop-sdk-author/scripts/validate_sdk_plan.py <sdk-plan.json>
```

The validator is intentionally narrow. Passing it means the plan shape and
forbidden app-stack/schema-copy checks passed; it does not prove generated SDK
code compiles.
