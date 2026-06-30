# Stack-Neutral SDK Plan Schema

This reference defines the `sdk-plan.json` shape used by `loop-sdk-author`.
The plan is a derived handoff artifact, not a source document.

## Core Rules

- Keep the plan stack-neutral. It may prepare an SDK before any consuming
  application exists.
- Do not copy OpenAPI schemas. Use `contract_pointer` values that point to
  `openapi.yaml`.
- Use `integration-contract.json` pointers for crypto, signing, callbacks,
  field conditions, and contract tests.
- Use `handoff/sdk-hints.json` for grouping and implementation notes.
- Put missing or unsupported source facts in `gaps`.

## Required Top-Level Fields

```json
{
  "version": "1.0",
  "source_run_dir": "output/<run-id>",
  "contracts": {
    "openapi": "../openapi.yaml",
    "integration": "../integration-contract.json",
    "sdk_hints": "../handoff/sdk-hints.json"
  },
  "runtime": {
    "config": []
  },
  "operation_groups": [],
  "operations": [],
  "mechanisms": {
    "auth": [],
    "crypto": [],
    "callbacks": []
  },
  "adapters": [],
  "gaps": []
}
```

## Field Guidance

### `runtime.config`

List runtime values the SDK consumer must provide:

```json
{
  "name": "base_url",
  "source": "../openapi.yaml#/servers/0/url",
  "required": true
}
```

Secrets and IVs must point to `integration-contract.json`, not inline secret
values.

### `operation_groups`

Mirror OpenAPI tags or `handoff/sdk-hints.json` groups:

```json
{
  "name": "Payments",
  "operations": ["createPayment"]
}
```

### `operations`

Each operation must link back to the contract and avoid schema copies:

```json
{
  "operation_id": "createPayment",
  "method": "POST",
  "path": "/payments",
  "contract_pointer": "../openapi.yaml#/paths/~1payments/post",
  "sdk_method": "create_payment",
  "requires": ["runtime:base_url", "crypto:TradeInfo"],
  "gaps": []
}
```

Do not include `requestBody`, `responses`, `components`, `schemas`, or
`properties` in this plan. SDK generators can dereference OpenAPI later.

### `mechanisms`

Use pointers into `integration-contract.json`:

```json
{
  "name": "TradeInfo",
  "contract_pointer": "../integration-contract.json#/crypto/0",
  "purpose": "request"
}
```

### `adapters`

Leave this empty for a neutral plan. If the user explicitly requests a target
language, entries may describe language-level packaging only:

```json
{
  "language": "typescript",
  "package_name": "@example/pay-sdk",
  "http_layer": "fetch",
  "contract_pointer": "../openapi.yaml"
}
```

Do not name application frameworks in adapters.

## Forbidden Content

Forbidden keys:

- `framework`
- `app_stack`
- `ui_framework`
- `web_framework`
- `database`
- `orm`
- `controller`
- `middleware`
- `route`
- `component`
- `requestBody`
- `responses`
- `components`
- `schemas`
- `properties`

Forbidden framework terms in string values:

- `React`
- `Next.js`
- `Vue`
- `Angular`
- `Nuxt`
- `SvelteKit`
- `Django`
- `FastAPI`
- `Flask`
- `Laravel`
- `Rails`
- `Spring Boot`
- `NestJS`
- `Remix`

Use `scripts/validate_sdk_plan.py` to enforce this baseline.
