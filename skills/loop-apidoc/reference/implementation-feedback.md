# Implementation feedback and Effective Contracts

Use this workflow only for passive, normalized implementation evidence. Supplier sources remain
the sole authority for the Normative Contract. An observation can confirm, contradict, be
inconclusive, or be out of scope only for its exact Applicability Envelope; it never becomes
`explicit_support` or `derived_support`.

## Preconditions

- The requested Foundry asset is approved and contains `core/contract.json`,
  `core/evidence.json`, and `core/relationships.json`.
- The Observation Bundle uses `implementation-observation-bundle/v1` and
  `conformance/v1` / `redaction/v1`.
- Every observation binds the exact base contract digest, operation, material claim/path,
  producer, runner, replay recipe, probe digest, fixture digest, bounded attempts, and
  digest-verified sanitized facts.
- Observation kinds are a semantic allowlist: status/success binds the same operation's
  `/responses/<status>/status_code`; response field/type binds a response-referenced schema and
  the matching `/fields/.../name` or `/fields/.../type`. Mismatches fail closed.
- The Applicability Envelope includes provider/product, environment, endpoint identity,
  authentication role, client/harness versions, test-data class, and a timezone-aware window.
- Do not persist raw bodies, Authorization/Cookie values, credentials, tokens, PII, or
  low-entropy secrets. The pre-output input gate deterministically rejects sensitive field names and
  obvious email, phone, national-ID, SSN, passport, and Luhn-valid payment-card values. Low-entropy PII must be omitted, never
  retained as a hash. API response observations require allowlisted sanitized facts.
- Observation IDs, attempt IDs, and evidence fragment IDs are unique across the entire bundle;
  duplicate identifiers fail before assessment so lineage references remain unambiguous.

## Governed workflow

All output paths for `assess`, `propose`, `compose`, and `provider-erratum` must stay outside
`.foundry`. These commands perform no network I/O.

```bash
<APIDOC> feedback assess --project "<PROJECT>" --docset "<DOCSET>" \
  --asset "<BASE_ASSET>" --bundle "<BUNDLE.json>" --output "<ASSESSMENT_DIR>"

<APIDOC> feedback propose \
  --assessment "<ASSESSMENT_DIR>/feedback-assessment.json" \
  --at "<TIMEZONE_AWARE_TIME>" --output "<PROPOSALS_DIR>"

<APIDOC> feedback submit --project "<PROJECT>" --docset "<DOCSET>" \
  --bundle "<BUNDLE.json>" \
  --assessment "<ASSESSMENT_DIR>/feedback-assessment.json" \
  [--proposal "<PROPOSALS_DIR>/<PROPOSAL_ID>.json"]

<APIDOC> feedback review --project "<PROJECT>" --docset "<DOCSET>" \
  --case "<ASSESSMENT_ID>" --reviewed-by "<HUMAN_ID>" \
  --reviewer-version "<VERSION>" --at "<TIMEZONE_AWARE_TIME>" \
  --disposition "<rejected|needs_evidence>" --route "<CORRECTIVE_ROUTE>" \
  [--rationale "<RATIONALE>"]

<APIDOC> feedback approve --project "<PROJECT>" --docset "<DOCSET>" \
  --case "<ASSESSMENT_ID>" --approved-by "<HUMAN_ID>" \
  --approver-version "<VERSION>" --at "<TIMEZONE_AWARE_TIME>" \
  --expires-at "<TIMEZONE_AWARE_EXPIRY>" \
  [--revalidation-trigger "<TRIGGER>" ...] \
  [--supersedes-amendment "<AMENDMENT_ID>"]
```

`submit` creates the immutable candidate, with or without a proposal. `review` records its one
write-once non-approval decision (`rejected` or `needs_evidence`) and corrective route; it works
for either case shape. Its route must not be `closed_no_change` or `amendment_proposal`.
Proposal time must not precede the Observation Bundle's `observed_until`. A non-approval review
time must not precede observation completion and, when the case has a proposal, must not precede
`proposal.created_at`.
`approve` requires a named human identity different from the producer and runner, binds the
decision to every relevant digest, creates an expiring Compatibility Amendment, composes prior
exact-scope amendment lineage, and publishes a new immutable Effective release. It never changes
the normative global `current.json`. Same-target active amendments fail closed unless an explicit
same-scope/same-target supersession is declared. `review` and `approve` are mutually exclusive
write-once decisions for a case; neither silently replaces the other.
Repeatable free-text `revalidation_triggers` are review declarations only. There is no external
trigger-signal contract, so they do not automatically execute or schedule revalidation.
Approval loads governed amendment lineage only after the exact-scope current head passes the
same integrity read used by `feedback current`. The pointer's `effective_asset_digest` binds the
complete strict-validated canonical `EffectiveAsset`, including all declared fields; unknown
fields fail closed. Every successor must provide `supersedes` together with
`supersedes_asset_digest`, forming an immutable hash chain. Governed and user-facing traversal
verifies each predecessor asset digest and amendment artifact digest before following the next
link. Explicit supersession by a new reviewed amendment may recover expired lineage; any
historical asset metadata, amendment, or supersession tampering must fail closed before it can
contaminate approval/composition.

Assessment selects one of all eight deterministic routes:

| Evidence outcome | Route |
| --- | --- |
| all material observations confirm | `closed_no_change` |
| other inconclusive evidence | `needs_evidence` |
| high-risk contradiction | `provider_clarification` |
| harness or fixture failure | `implementation_correction` |
| out-of-scope evidence, or DNS/proxy/gateway failure | `environment_configuration_correction` |
| policy-safe contradiction without documentary evidence | `extraction_correction` |
| repeated network/timeout/rate-limit failure | `provider_runtime_regression_review` |
| policy-safe, documentary-grounded contradiction | `amendment_proposal` |

Only `confirms` and `contradicts` count as assessed material claims. `inconclusive` and
`out_of_scope` remain untested and open; composition also reports
`unresolved_contradiction_count` rather than treating an unapplied contradiction as resolved.

Proposal and composition integrity bind the digest of the complete Normative release:
contract, documentary fragments, and support relationships. A change to any of those
authority-bearing inputs makes the proposal/amendment stale and fails closed.

Exit meanings are command-specific: `assess` exits 1 when discrepancies remain; `propose`
exits 1 when no proposal is warranted; `compose` exits 1 when stale/expired discrepancies are
surfaced; `review` exits 0 only after the decision is recorded; input/integrity failures exit 2.
A proposal is never authority until independent approval succeeds.

## Query and dry-run composition

```bash
<APIDOC> feedback compose --project "<PROJECT>" --docset "<DOCSET>" \
  --asset "<BASE_ASSET>" --target "<APPLICABILITY.json>" \
  --amendment "<APPROVED_AMENDMENT.json>" [--amendment "<OTHER.json>" ...] \
  --at "<TIMEZONE_AWARE_TIME>" --output "<COMPOSE_DIR>"

<APIDOC> feedback current --project "<PROJECT>" --docset "<DOCSET>" \
  --target "<APPLICABILITY.json>" --at "<TIMEZONE_AWARE_TIME>"
```

`current` resolves only the exact scope digest at the supplied time. It rejects a query before
the approval/composition time, an expired Effective release, a base that is no longer normative
`current`, and stale pointer or bounded artifact bindings. The pointer also binds the complete
strict-validated canonical `EffectiveAsset`, including every declared field, through
`effective_asset_digest`; unknown fields fail closed. Each Effective asset and pointer binds
three immutable artifacts independently: `effective-contract.json`,
`compatibility-amendment.json`, and `provenance.json`; `current` bounds, parses, digest-checks,
and cross-checks all three. It accepts only `APPROVED` and cross-validates contract identity,
amendment IDs, validity/counts, approval actor/time, and provenance approval/assessment/bundle
bindings. A successful JSON result includes `valid_until`, `open_discrepancy_count`,
`stale_amendment_count`, `untested_material_claim_count`, and
`unresolved_contradiction_count`. Never substitute a global Effective current. Each effective
value retains `normative` or `observed_override` authority plus its evidence and approval
lineage. Report open discrepancies, expired/stale/inapplicable/superseded amendments, coverage,
observation time, and suite version without claiming universal truth. Stale amendments reflect
verifiable release/contract/source/policy/approval-time drift; expired and inapplicable remain
separate. `foundry.query` owns the only governed lineage-traversal read-side I/O.

## Provider Erratum

A formal provider correction is supplier material, not an empirical amendment:

```bash
<APIDOC> feedback provider-erratum --metadata "<ERRATUM.json>" \
  --artifact "<LOCAL_ARTIFACT>" --output "<HANDOFF_DIR>"
```

This verifies the local artifact digest and writes a non-mutating supplemental-source handoff.
Then execute the complete normal flow: acquisition/preprocess → manifest → source-risk → agent
source-quality review → source-quality → extraction → verify-extraction → assemble → human
review → Foundry approval. Reassess observations against that new Normative release. Never use
the handoff itself to patch or publish either contract.
