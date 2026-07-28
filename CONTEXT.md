# API Contract Domain

This context names the source-grounded integration semantics that belong in the
canonical contract alongside endpoint and schema facts.

## Language

**Transport Policy**:
A source-stated, cross-operation rule for wire-level behavior such as protocol,
content type, HTTP status semantics, timezone, or timestamp format.
_Avoid_: Transport binding, endpoint transport

**Amount Direction**:
A source-stated relationship between an operation's amount and its balance effect,
including the accepted sign and precision when documented.
_Avoid_: Amount convention, inferred debit/credit

**Idempotency Rule**:
A source-stated duplicate or in-progress outcome and the caller action associated
with it, optionally scoped to operations or provider error codes.
_Avoid_: Error-code meaning, retry guess

**Line Currency Policy**:
A source-stated constraint on how a product line selects or binds currency. The
absence of a request currency field is not evidence of a single-currency policy.
_Avoid_: Currency inference, assumed single-currency line
