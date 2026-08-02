---
status: accepted
---

# Separate documentary and empirical authority

`loop-apidoc` keeps documentary grounding and implementation conformance as separate
authority axes. Supplier sources remain the sole authority for Normative Contract
claims; an Implementation Observation is empirical evidence only for behavior witnessed
within its Applicability Envelope and never becomes explicit or derived supplier-source
support. This separation prevents a finite, environment-dependent execution from being
generalized into provider intent while still making reproducible downstream discoveries
governable.

An Effective Contract is a deterministic, scope-specific composition of one approved
Normative Contract release and the active approved Compatibility Amendments applicable
to an exact target Applicability Envelope. Composition does not mutate the Normative
Contract or any approved asset, and every effective value retains its authority and
lineage. The exact-scope pointer's `effective_asset_digest` binds the complete strict-validated
canonical EffectiveAsset, including all declared fields; unknown fields fail closed. The
asset/pointer also binds the Effective Contract, Compatibility
Amendment, and Effective provenance artifacts. Every successor pairs `supersedes` with
`supersedes_asset_digest`, forming an immutable hash chain. Current resolution verifies these
bindings and all three artifacts. A formal Provider Erratum instead re-enters the existing
governed source pipeline because it can carry documentary authority.

Governed feedback and Effective JSON models reject unknown fields. Current resolution accepts
only `APPROVED`, cross-validates Effective Contract counts/validity/amendment IDs, approval
actor/time, and provenance approval/assessment/bundle bindings, and exposes a digest-bound
`stale_amendment_count`. Stale means verifiable release/contract/source/policy/approval-time
drift; expired and inapplicable remain separate. Free-text revalidation triggers are declarations
for human review, not automatic external signals. `foundry.query` is the one read-side I/O for
lineage traversal.

Assessment routing is deterministic and complete across eight outcomes: close with no
change, request more evidence, ask the provider for clarification, correct the implementation,
correct environment configuration, correct extraction, review a possible provider-runtime
regression, or propose an amendment. Harness/fixture failures belong to implementation;
out-of-scope and DNS/proxy/gateway failures belong to environment configuration; repeated
network/timeout/rate-limit failures belong to provider-runtime review; and a policy-safe
contradiction without documentary evidence belongs to extraction correction. Only confirmed
or contradicted targets count as assessed. Inconclusive and out-of-scope targets remain
untested and open, and unapplied contradictions remain visible as unresolved.

The observation allowlist is semantic: status/success observations must bind the same operation's
response-status path, and response field/type observations must bind a matching field name/type
path in a response-referenced schema. This pure policy lives in `core/conformance_policy.py`.

Submitting a case and deciding it are separate governance stages. A reviewer can record one
write-once non-approval decision (`rejected` or `needs_evidence`) for an immutable case with
or without a proposal, but must name a corrective route other than `closed_no_change` or
`amendment_proposal`. Approval remains a separate path that requires a proposal and publishes
an expiring exact-scope amendment. Proposal creation cannot precede observation-window
completion. A non-approval decision cannot precede observation completion and, when a proposal
exists, cannot precede its creation. Persisted feedback also passes a deterministic privacy gate:
sensitive field names and obvious email/phone/national-ID/SSN/passport/Luhn-valid payment-card values are rejected, while
low-entropy PII is omitted rather than transformed into a hash.

The first feedback workflow accepts passive, normalized evidence only. Active probing is
deferred until integrity validation, redaction, scope matching, deterministic assessment,
review, expiry, and conflict handling have been proven without granting the product
authority to call third-party systems.

## Considered options

- Rewriting the Canonical Contract directly from observed behavior would offer one
  convenient artifact but would conflate provider statements with local runtime facts.
- Treating observations as additional supplier evidence would reuse existing support
  relationships but would erase their different authority and applicability limits.
- Starting with active probes would accelerate acquisition but would combine governance
  design with credentials, network side effects, and third-party execution risk.

## Consequences

Documentary support and conformance results must be reported independently. Conflicting
or incomplete observations remain visible and fail closed; they cannot be resolved by
majority vote, last-write-wins, or an automatic contract patch. Compatibility Amendments
must remain approved, expiring, scope-bound overlays, and composition must reject
conflicting applicable amendments. Effective reads must report bounded validity,
open/untested counts, and unresolved contradictions; they must fail if any of their three
artifact bindings or lineage checks is stale.
Approval and user-facing lineage reads traverse supersession only after the same bound
exact-scope current-head read succeeds. Each hop verifies the predecessor EffectiveAsset digest
and amendment artifact digest before following the next `supersedes` link. This allows a new
reviewed amendment to recover expired lineage while making historical asset metadata, amendment,
or supersession tampering fail closed before it can contaminate later approval/composition.

**Falsified if:** an Implementation Observation changes supplier-source support; an
unconfirmed observed value mutates a Normative Contract or approved asset; an Effective
Contract applies an amendment outside its exact Applicability Envelope or loses authority
lineage; a global effective current replaces scope-specific selection; or active probing
is introduced before the passive-evidence governance boundary is enforced; a non-approval
review silently publishes an amendment; an inconclusive/out-of-scope target is counted as
assessed; or current resolution accepts a stale Effective Contract, amendment, or provenance
artifact; a decision predates its evidence/proposal; low-entropy PII is persisted as a hash; or
approval consumes lineage behind an unverified current head or an unverified predecessor digest.
