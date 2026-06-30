# Design: Stack-Neutral SDK Authoring Skill

- Date: 2026-06-30
- Status: implemented as project-local skill
- Scope: add an agent-facing SDK authoring workflow without changing the
  `loop-apidoc assemble` output contract.

## Goal

Allow an agent to prepare SDK work before the consuming application stack is
known. The SDK may be planned or generated from verified API contracts, but the
agent must not prebuild application-framework integration code.

## Architecture

Add a project-local skill:

```text
skills/loop-sdk-author/
  SKILL.md
  agents/openai.yaml
  reference/sdk-plan-schema.md
  scripts/validate_sdk_plan.py
```

The skill consumes only completed `loop-apidoc` run artifacts:

- `openapi.yaml`
- `integration-contract.json`
- `handoff/sdk-hints.json`
- `examples/` as derived navigation aid
- `validation/report.*` for known blockers

The default output is a derived `sdk-plan.json`, preferably written under
`<run-dir>/handoff/sdk-plan.json` when the user asks for a file.

## Boundary

This is deliberately not part of `assemble`. The existing pipeline produces
source-grounded API contracts and handoff hints; SDK authoring is a downstream
engineering activity. Keeping it as a skill avoids expanding the core validation
surface to language runtimes and package build systems.

The validation script is narrow and deterministic. It rejects:

- application stack/framework fields or framework terms;
- schema copies such as `requestBody`, `responses`, `components`, `schemas`, or
  `properties`;
- missing required `sdk-plan.json` sections;
- operations without OpenAPI `contract_pointer` links.

## Acceptance

- Skill is discoverable under `skills/loop-sdk-author`.
- Skill states that application stack, UI, ORM, routes, controllers, and
  deployment are out of scope.
- `sdk-plan.json` schema reference defines the neutral plan shape.
- Validator accepts a minimal neutral plan and rejects app-stack/schema-copy
  violations.
- Existing `loop-apidoc` pipeline behavior is unchanged.
