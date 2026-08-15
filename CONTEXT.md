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

**Normative Contract**:
The supplier-source-grounded Canonical Contract describing what the provider states.
Supplier sources are its sole authority.
_Avoid_: Effective contract, observed contract

**Implementation Observation**:
Immutable empirical evidence of behavior witnessed within one declared Applicability
Envelope; it is not supplier-source support.
_Avoid_: Runtime truth, normative evidence

**Applicability Envelope**:
The declared provider, deployment, environment, identity, configuration, client, data,
and time boundaries within which an Implementation Observation may be interpreted.
_Avoid_: Global scope, universal applicability

**Conformance Finding**:
A deterministic relationship between a material Normative Contract claim and an
Implementation Observation, reported without changing either claim's authority.
_Avoid_: Contract correction, source finding

**Provider Erratum**:
A formal provider correction that is supplemental supplier source material and may
change a Normative Contract only through the governed source pipeline.
_Avoid_: Compatibility amendment, local workaround

**Compatibility Amendment**:
A reviewed, approved, expiring, and scope-bound addition or correction supported by
reproducible Implementation Observations when no Provider Erratum exists.
_Avoid_: Normative update, automatic patch

**Effective Contract**:
The deterministic composition of one approved Normative Contract release and the
active Compatibility Amendments applicable to one exact target Applicability Envelope.
_Avoid_: Mutated canonical contract, global effective truth

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

**Coverage Directive**:
A requester-authored instruction naming a scope of attention the extraction should sweep
exhaustively. Reporting that no source states it is a complete answer, not a failure.
_Avoid_: Hint, preference, soft requirement

**Expectation Directive**:
A requester-authored existence claim that supplier sources document a specific operation,
field, or error code. It is falsified — not satisfied — when no source states it, and a
falsified claim fails validation.
_Avoid_: Required field, feature request, must-have

**Focus Response**:
The agent's one-to-one answer to each directive, resolved either to deterministic anchors
carrying exact evidence, or to a not-found outcome naming every readable source searched.
It has no third outcome; a directive's applicability is the requester's judgement, never
the agent's.
_Avoid_: Extraction result, missing list, directive status

**Documented Error-Code Floor**:
The set of provider error codes the supplier sources demonstrably document through
structure they themselves present, and the deterministic basis for judging whether an
exhaustive answer collected them all. It is a lower bound: an answer naming more codes is
still complete. Where the sources present no such structure the floor does not exist,
which is not the same as being empty.
_Avoid_: Expected code list, error-code count, required errors

**Line Currency Policy**:
A source-stated constraint on how a product line selects or binds currency. The
absence of a request currency field is not evidence of a single-currency policy.
It belongs to the Payment Profile.
_Avoid_: Currency inference, assumed single-currency line
