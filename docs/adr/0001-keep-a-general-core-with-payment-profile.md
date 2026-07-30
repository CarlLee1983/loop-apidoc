---
status: accepted
---

# Keep a general contract core with an optional payment profile

`loop-apidoc` remains a domain-neutral, source-grounded API contract product rather
than becoming a payment-only product. Payment and wallet integrations are an important
initial vertical, so their recurring source-stated semantics may use an optional Payment
Profile governed by the same exact-evidence and fail-closed rules as the Canonical
Contract Core. Transport policy and idempotency remain general integration semantics;
amount direction and line-currency policy belong to the Payment Profile. A new
industry-specific typed concept is admitted only when it recurs across providers, has a
named downstream consumer, cannot be represented faithfully by an existing generic
constraint, and has source-backed benchmark coverage. The v0.27 serialized collections
remain compatible through derived top-level views while the Canonical Contract stores
their state only in the optional Payment Profile.

## Considered options

- Making payment the whole product would match much of the current benchmark corpus but
  would contradict the existing cross-industry API-documentation scope.
- Keeping every industry concept directly in the core would avoid a migration now but
  would let benchmark composition silently determine the product ontology.

## Consequences

Payment-specific concepts must not become prerequisites for non-payment contracts.
`GroundedApiContract` owns at most one optional `PaymentProfile`; amount direction and
line-currency policy live only there. The legacy top-level collection names remain a
read/write compatibility adapter derived from that profile, so they do not create a
second source of state. `integration.json` input and generated artifact shapes remain
unchanged.

**Falsified if:** a payment-specific concept stops being optional for a non-payment
contract. Concretely, this decision no longer holds when `amount_direction` or
`line_currency_policy` becomes a required field, a non-empty default, or a validation
prerequisite in `loop_apidoc/agentcli/input_schema.py`, `loop_apidoc/plan/models.py`,
`loop_apidoc/domain/models.py`, or `loop_apidoc/validate/integration.py` — that is, when
a contract carrying neither can no longer reach a passing validation report.
