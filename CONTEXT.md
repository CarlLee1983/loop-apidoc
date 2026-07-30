# API Contract Domain

This context names the source-grounded semantics shared by the canonical contract
and the optional domain profiles that extend it.

## Language

**Canonical Contract Core**:
The domain-neutral contract facts and evidence rules shared by every supported
integration, regardless of industry or protocol.
_Avoid_: Generic API model, base payment contract

**Domain Profile**:
An optional vocabulary of source-stated semantics for one industry or integration
domain, governed by the same evidence and fail-closed rules as the core.
_Avoid_: Core extension field, vendor special case

**Payment Profile**:
The Domain Profile for payment and wallet semantics that are not meaningful to every
API contract. It owns Amount Direction and Line Currency Policy; contracts without
those semantics have no Payment Profile.
_Avoid_: Payment core, universal integration semantics

**Projection Input**:
The self-contained Core boundary value containing one Canonical Contract, its exact
Source Set identity, and its Evidence Bundle.
_Avoid_: protocol extraction, projection config

**Protocol Projection Compiler**:
A deterministic GraphQL or AsyncAPI compiler over the Canonical Contract. It remains a
tested Core seam, not a public run workflow, until a named downstream consumer defines
the required source and acceptance contract.
_Avoid_: protocol run, alternate assemble, OpenAPI conversion

**Transport Policy**:
A source-stated, cross-operation rule for wire-level behavior such as protocol,
content type, HTTP status semantics, timezone, or timestamp format.
_Avoid_: Transport binding, endpoint transport

**Amount Direction**:
A source-stated relationship between an operation's amount and its balance effect,
including the accepted sign and precision when documented. It belongs to the Payment
Profile.
_Avoid_: Amount convention, inferred debit/credit

**Idempotency Rule**:
A source-stated duplicate or in-progress outcome and the caller action associated
with it, optionally scoped to operations or provider error codes.
_Avoid_: Error-code meaning, retry guess

**Line Currency Policy**:
A source-stated constraint on how a product line selects or binds currency. The
absence of a request currency field is not evidence of a single-currency policy.
It belongs to the Payment Profile.
_Avoid_: Currency inference, assumed single-currency line
