# Claim-Level Semantic Evidence Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Core accept a `GroundedClaim` only when deterministic, claim-path-specific
relationships bind every projected leaf to exact source fragments, while introducing the
behavior through the non-authoritative shadow architecture.

**Architecture:** Add typed Evidence Ledger and support-graph values to Domain, pure
verification and coverage reconciliation to Core, exact-fragment acquisition to adapters,
and a conservative legacy-to-support bridge in shadow. Keep the shipping legacy
plan/generate/validate path authoritative and expose richer Core OpenAPI, review, and
provenance only as observational shadow projections.

**Tech Stack:** Python 3.11+, Pydantic v2 frozen models, SHA-256/canonical JSON/Unicode NFC
from the standard library, PyYAML, PyMuPDF, existing Markdown source-fact scanner, pytest,
pytest-cov, and Ruff.

## Global Constraints

- Source documents are the only source of truth; absent facts remain null/missing.
- Core and Domain perform no filesystem, network, model, process, browser, CLI, or database
  I/O.
- Runtime proposals and confidence never decide claim status.
- A whole-document, unresolved, reconstruction-only, invalid-digest, or inapplicable
  fragment never produces semantic support.
- Every projected material claim path requires `explicit_support` or deterministically
  validated `derived_support`.
- `evidence_refs` remains readable for compatibility but Core status logic never reads it.
- Legacy CLI behavior, artifacts, validation, score, approval, Foundry, run status, and
  exit codes remain authoritative and unchanged.
- Shadow failure is observational and cannot change any legacy outcome.
- Legacy citations that cannot be materialized precisely become
  `insufficient/unverified`.
- No embedding or fuzzy-similarity score is sufficient for support.
- Total test coverage remains at or above 95%; Ruff and `git diff --check` must pass.
- Execute inline unless the user explicitly requests subagent delegation.

---

## File Structure

### New files

| File | Responsibility |
| --- | --- |
| `loop_apidoc/domain/evidence.py` | Typed locators, immutable source/evidence values, normalization, digest/ID helpers, support relationship values |
| `loop_apidoc/domain/claim_paths.py` | Enumerate and resolve stable material paths inside canonical claim values |
| `loop_apidoc/core/verification.py` | Validate evidence-bundle invariants and deterministically produce relationships |
| `loop_apidoc/adapters/fragments.py` | Read local sources and materialize precise fragments outside Core/Domain |
| `tests/domain/test_evidence.py` | Locator, normalization, digest, identity, hierarchy contracts |
| `tests/domain/test_claim_paths.py` | Stable semantic path enumeration/lookup |
| `tests/core/test_verification.py` | Exact/table/structured/enum/source-fact verification |
| `tests/adapters/test_fragments.py` | Markdown/PDF/JSON/YAML fragment acquisition |

### Main modified files

| File | Responsibility after change |
| --- | --- |
| `loop_apidoc/core/models.py` | Re-export evidence values; add support proposals and relationships to proposal/claim models |
| `loop_apidoc/core/reconciliation.py` | Reconcile verified relationships and complete claim-path coverage |
| `loop_apidoc/core/service.py` | Pass full bundles to reconciliation and evidence-aware projection compilation |
| `loop_apidoc/adapters/runtime.py` | Enforce support-proposal fragment scope |
| `loop_apidoc/domain/models.py` | Additive evidence bindings and relationship-bearing contract claims/conflicts |
| `loop_apidoc/domain/builder.py` | Preserve relationships and attach bindings to exact aggregate children |
| `loop_apidoc/domain/rules.py` | Deterministic semantic-support findings |
| `loop_apidoc/domain/projections.py` | Evidence-aware OpenAPI/review/provenance compilers |
| `loop_apidoc/source_facts/models.py` | Exact endpoint/table/cell/fence facts |
| `loop_apidoc/source_facts/markdown.py` | Preserve exact coordinates/content while retaining current conservative scanning |
| `loop_apidoc/shadow/bridge.py` | Build exact/degraded fragments and support proposals from legacy plan/source facts |
| `loop_apidoc/shadow/runner.py` | Acquire fragments, execute Core verification, compile projections |
| `loop_apidoc/shadow/models.py` | Relationship/projection artifact values and comparison diagnostics |
| `loop_apidoc/shadow/report.py` | Write new relationship/projection observational artifacts safely |
| `loop_apidoc/agentcli/assemble.py` | Reuse collected facts and pass source scope into safe shadow execution |
| `loop_apidoc/evaluation/models.py` | Expected relationships and semantic-support metrics |
| `loop_apidoc/evaluation/metrics.py` | Relationship correctness and claim support coverage metrics |
| `loop_apidoc/evaluation/replay.py` | Evaluate support proposals without production mutation |

---

### Task 1: Typed Evidence Ledger Contracts

**Files:**
- Create: `loop_apidoc/domain/evidence.py`
- Modify: `loop_apidoc/domain/__init__.py`
- Modify: `loop_apidoc/core/models.py`
- Create: `tests/domain/test_evidence.py`
- Modify: `tests/integration/test_evidence_to_release.py`
- Modify: `tests/adapters/test_local.py`

**Interfaces:**
- Produces: `FragmentLocator`, all locator variants, `FragmentPrecision`,
  `FragmentReconstructionRef`, `TransformationStep`, `SourceDescriptor`, `SourceSet`,
  `SourceArtifact`, `EvidenceFragment`, `EvidenceBundle`, `SupportRelationshipType`,
  `VerificationMethod`, `DerivationStep`, `ClaimSupportProposal`,
  `ClaimEvidenceRelationship`.
- Produces pure helpers:
  `normalize_excerpt(str) -> str`,
  `canonical_json(object) -> str`,
  `fragment_digest(str) -> str`,
  `make_fragment_id(...) -> str`,
  `make_relationship_id(...) -> str`.
- Preserves imports such as
  `from loop_apidoc.core.models import EvidenceFragment`.

- [ ] **Step 1: Write failing locator, digest, and hierarchy-value tests**

```python
from loop_apidoc.domain.evidence import (
    EvidenceFragment,
    FragmentPrecision,
    LineRangeLocator,
    TableCellLocator,
    fragment_digest,
    make_fragment_id,
    normalize_excerpt,
)


def test_fragment_digest_uses_normalized_fragment_content():
    normalized = normalize_excerpt("\r\nAmount  \r\n100\r\n")
    assert normalized == "Amount\n100"
    assert fragment_digest(normalized) == (
        "a8b72a7dc25c65357c83d7b1763d7032326615c36933bc8eb07f60603af4be87"
    )


def test_locator_and_fragment_id_are_stable():
    locator = TableCellLocator(
        table_index=1,
        row_index=2,
        column_index=3,
        row_key="amount",
        column_name="Required",
    )
    first = make_fragment_id(
        source_artifact_id="artifact-1",
        locator=locator,
        fragment_digest="a" * 64,
        parent_fragment_id="fragment-parent",
    )
    second = make_fragment_id(
        source_artifact_id="artifact-1",
        locator=locator.model_copy(),
        fragment_digest="a" * 64,
        parent_fragment_id="fragment-parent",
    )
    assert first == second


def test_exact_fragment_requires_content_or_reconstruction_reference():
    with pytest.raises(ValidationError):
        EvidenceFragment(
            id="fragment-x",
            source_artifact_id="artifact-1",
            locator=LineRangeLocator(start_line=2, end_line=3),
            fragment_digest="a" * 64,
            precision=FragmentPrecision.EXACT,
        )


def test_legacy_string_locator_deserializes_without_becoming_exact():
    whole = EvidenceFragment.model_validate(_legacy_fragment(locator="whole"))
    ambiguous = EvidenceFragment.model_validate(_legacy_fragment(locator="p.2"))
    assert whole.locator.kind == "whole_document"
    assert whole.precision is FragmentPrecision.DOCUMENT
    assert ambiguous.locator.kind == "unresolved"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run pytest tests/domain/test_evidence.py -q
```

Expected: collection fails because `loop_apidoc.domain.evidence` does not exist.

- [ ] **Step 3: Implement locator and immutable Evidence Ledger values**

Use a discriminated union and exact validation:

```python
FragmentLocator = Annotated[
    WholeDocumentLocator
    | PageLocator
    | LineRangeLocator
    | SectionLocator
    | TableLocator
    | TableCellLocator
    | JsonPointerLocator
    | CssSelectorLocator
    | XPathLocator
    | UnresolvedLocator,
    Field(discriminator="kind"),
]


class EvidenceFragment(FrozenModel):
    id: str
    source_artifact_id: str
    locator: FragmentLocator
    fragment_digest: str
    normalized_excerpt: str | None = None
    reconstruction_ref: FragmentReconstructionRef | None = None
    semantic_value: Any = None
    semantic_role: str | None = None
    parent_fragment_id: str | None = None
    precision: FragmentPrecision = FragmentPrecision.DOCUMENT
    transformation: tuple[TransformationStep, ...] = ()

    @field_validator("locator", mode="before")
    @classmethod
    def normalize_legacy_locator(cls, value: Any) -> Any:
        if value == "whole":
            return {"kind": "whole_document"}
        if isinstance(value, str):
            return {
                "kind": "unresolved",
                "raw": value,
                "reason": "legacy string locator",
            }
        return value

    @model_validator(mode="after")
    def exact_content_is_reconstructable(self) -> EvidenceFragment:
        if (
            self.precision is FragmentPrecision.EXACT
            and self.normalized_excerpt is None
            and self.reconstruction_ref is None
        ):
            raise ValueError("exact fragment requires excerpt or reconstruction reference")
        return self
```

Normalize with `unicodedata.normalize("NFC", value)`, canonicalize model payloads with
`model_dump(mode="json", exclude_none=True)`, and hash only UTF-8 bytes from canonical
values.

- [ ] **Step 4: Re-export moved values and update old whole-document fixtures**

In `core/models.py`, import the evidence types so old imports remain valid:

```python
from loop_apidoc.domain.evidence import (
    ClaimEvidenceRelationship,
    ClaimSupportProposal,
    EvidenceBundle,
    EvidenceFragment,
    SourceArtifact,
    SourceDescriptor,
    SourceSet,
)
```

Delete the duplicate Core definitions. Update existing whole-document fixtures to use:

```python
EvidenceFragment(
    id="fragment-1",
    source_artifact_id="artifact-1",
    locator=WholeDocumentLocator(),
    fragment_digest="b" * 64,
    precision=FragmentPrecision.DOCUMENT,
)
```

- [ ] **Step 5: Run focused tests to verify GREEN**

Run:

```bash
uv run pytest tests/domain/test_evidence.py \
  tests/integration/test_evidence_to_release.py tests/adapters/test_local.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the value-contract slice**

```bash
git add loop_apidoc/domain/evidence.py loop_apidoc/domain/__init__.py \
  loop_apidoc/core/models.py tests/domain/test_evidence.py \
  tests/integration/test_evidence_to_release.py tests/adapters/test_local.py
git commit -m "feat: add typed evidence fragment contracts"
```

### Task 2: Stable Claim Paths

**Files:**
- Create: `loop_apidoc/domain/claim_paths.py`
- Create: `tests/domain/test_claim_paths.py`

**Interfaces:**
- Produces:
  `material_claim_paths(claim_kind: str, value: Any) -> tuple[str, ...]`,
  `claim_value_at(claim_kind: str, value: Any, path: str) -> Any`,
  `escape_segment(str) -> str`.
- Semantic collections are addressed by parameter `(location, name)`, response status,
  schema-field name, security-scheme name, and operation reference rather than list index.

- [ ] **Step 1: Write failing stable-path tests**

```python
def test_operation_paths_are_keyed_by_parameter_and_response_identity():
    value = {
        "method": "POST",
        "path": "/payments",
        "parameters": [
            {"name": "currency", "location": "query", "required": True},
            {"name": "amount", "location": "query", "required": True},
        ],
        "responses": [{"status_code": "200", "description": "OK"}],
    }
    assert material_claim_paths("operation", value) == (
        "/method",
        "/parameters/query/amount/name",
        "/parameters/query/amount/required",
        "/parameters/query/currency/name",
        "/parameters/query/currency/required",
        "/path",
        "/responses/200/description",
        "/responses/200/status_code",
    )
    assert claim_value_at(
        "operation", value, "/parameters/query/amount/required"
    ) is True


def test_dynamic_segments_use_rfc6901_escaping():
    value = {"name": "Envelope", "fields": [{"name": "a/b~c", "type": "string"}]}
    assert "/fields/a~1b~0c/type" in material_claim_paths("schema", value)
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run pytest tests/domain/test_claim_paths.py -q
```

Expected: import failure for `domain.claim_paths`.

- [ ] **Step 3: Implement domain-specific path enumeration and lookup**

Implement explicit handlers rather than a generic recursive list-index walker:

```python
_PATH_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "operation": _operation_paths,
    "schema": _schema_paths,
    "environment": _environment_paths,
    "security": _security_paths,
    "error": _error_paths,
    "webhook": _webhook_paths,
    "integration_mechanic": _integration_paths,
    "operational_constraint": _operational_paths,
}


def material_claim_paths(claim_kind: str, value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, dict) or claim_kind not in _PATH_HANDLERS:
        return ("",)
    return tuple(sorted(_PATH_HANDLERS[claim_kind](value)))


def claim_value_at(claim_kind: str, value: Any, path: str) -> Any:
    values = {"": value}
    if isinstance(value, dict) and claim_kind in _PATH_HANDLERS:
        values.update(_PATH_HANDLERS[claim_kind](value))
    if path not in values:
        raise ClaimPathError(f"unknown material claim path: {path}")
    return values[path]
```

Include `name`/`status_code` material leaves because those values also enter projections.
Exclude absent optionals and empty collections.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
uv run pytest tests/domain/test_claim_paths.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/domain/claim_paths.py tests/domain/test_claim_paths.py
git commit -m "feat: define stable material claim paths"
```

### Task 3: Deterministic Support Verification

**Files:**
- Create: `loop_apidoc/core/verification.py`
- Create: `tests/core/test_verification.py`
- Modify: `loop_apidoc/core/models.py`
- Modify: `tests/adapters/test_runtime.py`
- Modify: `loop_apidoc/adapters/runtime.py`

**Interfaces:**
- `validate_evidence_bundle(bundle: EvidenceBundle) -> tuple[EvidenceViolation, ...]`
- `verify_claim_support(proposal: ClaimProposal, bundle: EvidenceBundle)
  -> tuple[ClaimEvidenceRelationship, ...]`
- `ClaimProposal.support_proposals: tuple[ClaimSupportProposal, ...] = ()`
- Runtime scope includes every `support_proposals[].fragment_id`.

- [ ] **Step 1: Write failing exact, table-cell, whole-document, and mismatch tests**

```python
def test_table_cell_supports_matching_field_path():
    proposal = _operation_proposal(
        value=_operation(required=True),
        supports=(
            _support(
                "fragment-required",
                "/parameters/query/amount/required",
                VerificationMethod.TABLE_CELL_MAPPING,
            ),
        ),
    )
    relationship = verify_claim_support(proposal, _bundle(
        _cell_fragment(
            "fragment-required",
            excerpt="Y",
            semantic_value=True,
            column_name="Required",
        )
    ))[0]
    assert relationship.relationship is SupportRelationshipType.EXPLICIT_SUPPORT
    assert relationship.claim_path == "/parameters/query/amount/required"


def test_whole_document_reference_is_insufficient():
    relationship = verify_claim_support(
        _scalar_proposal("Demo", "fragment-whole"),
        _bundle(_whole_fragment("fragment-whole")),
    )[0]
    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == "FRAGMENT_NOT_EXACT"


def test_different_exact_value_contradicts_claim():
    relationship = verify_claim_support(
        _scalar_proposal("USD", "fragment-currency"),
        _bundle(_line_fragment("fragment-currency", "TWD")),
    )[0]
    assert relationship.relationship is SupportRelationshipType.CONTRADICTS
    assert relationship.observed_value == "TWD"


def test_unequal_page_scope_is_insufficient_not_a_false_contradiction():
    relationship = verify_claim_support(
        _scalar_proposal("USD", "fragment-page"),
        _bundle(_page_fragment("fragment-page", "Currencies: USD and TWD")),
    )[0]
    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == "FRAGMENT_NOT_VALUE_BEARING"
```

- [ ] **Step 2: Write failing structured-path, enum, digest, and hierarchy tests**

```python
def test_json_pointer_support_uses_canonical_structured_value():
    relationship = verify_claim_support(
        _proposal(value={"type": "string"}, method=VerificationMethod.STRUCTURED_FIELD_PATH),
        _bundle(_json_fragment(pointer="/components/schemas/Id", value={"type": "string"})),
    )[0]
    assert relationship.relationship is SupportRelationshipType.EXPLICIT_SUPPORT


def test_invalid_fragment_digest_is_insufficient():
    relationship = verify_claim_support(
        _scalar_proposal("USD", "fragment-bad"),
        _bundle(_line_fragment("fragment-bad", "USD", digest="0" * 64)),
    )[0]
    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == "FRAGMENT_DIGEST_MISMATCH"


@pytest.mark.parametrize("bundle", [
    _bundle_with_missing_parent(),
    _bundle_with_cross_artifact_parent(),
    _bundle_with_cycle(),
])
def test_invalid_fragment_hierarchy_is_reported(bundle):
    assert validate_evidence_bundle(bundle)
```

- [ ] **Step 3: Run verification tests to verify RED**

Run:

```bash
uv run pytest tests/core/test_verification.py -q
```

Expected: import failure for `core.verification` or missing support fields.

- [ ] **Step 4: Implement applicability checks and relationship classification**

The verifier must use this decision order:

```python
def _verify_one(
    claim_identity: str,
    claim_kind: str,
    value: Any,
    support: ClaimSupportProposal,
    fragments: Mapping[str, EvidenceFragment],
) -> ClaimEvidenceRelationship:
    fragment = fragments.get(support.fragment_id)
    if fragment is None:
        return _insufficient_relationship(
            claim_identity=claim_identity,
            support=support,
            fragment=None,
            reason_code="FRAGMENT_NOT_FOUND",
        )
    if fragment.precision is not FragmentPrecision.EXACT:
        return _insufficient_relationship(
            claim_identity=claim_identity,
            support=support,
            fragment=fragment,
            reason_code="FRAGMENT_NOT_EXACT",
        )
    if fragment.normalized_excerpt is None:
        return _insufficient_relationship(
            claim_identity=claim_identity,
            support=support,
            fragment=fragment,
            reason_code="FRAGMENT_NOT_MATERIALIZED",
        )
    if fragment_digest(fragment.normalized_excerpt) != fragment.fragment_digest:
        return _insufficient_relationship(
            claim_identity=claim_identity,
            support=support,
            fragment=fragment,
            reason_code="FRAGMENT_DIGEST_MISMATCH",
        )
    try:
        claim_value = claim_value_at(claim_kind, value, support.claim_path)
    except ClaimPathError:
        return _insufficient_relationship(
            claim_identity=claim_identity,
            support=support,
            fragment=fragment,
            reason_code="CLAIM_PATH_UNKNOWN",
        )
    comparison = _COMPARATORS[support.verification_method](
        claim_value, fragment, support
    )
    return _relationship_from_comparison(
        claim_identity, support, claim_value, fragment, comparison
    )
```

Comparator results are exactly `match`, `mismatch`, or `insufficient`; only `match`
creates the proposal's explicit/derived support kind. `mismatch` creates `contradicts`
only for a value-bearing table cell, JSON Pointer, or fragment with a deterministic
`semantic_role` and `semantic_value`. Unequal arbitrary page/section/line text and every
other non-decision create `insufficient`.

Allow `derived_support` only when every named derivation step is in the versioned allowlist
and recomputed output digests match.

- [ ] **Step 5: Make relationship IDs and ordering deterministic**

Canonicalize the complete final relationship payload, excluding `id`, and derive:

```python
digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:24]
relationship_id = f"relationship-{digest}"
```

Sort returned relationships by
`(claim_identity, claim_path, fragment_id, relationship.value, id)`.

- [ ] **Step 6: Extend runtime scope enforcement**

In `CallableRuntimeAdapter.propose`:

```python
refs = set(proposal.evidence_refs)
refs.update(item.fragment_id for item in proposal.support_proposals)
outside = refs - scope
if outside:
    raise RuntimeContractError(
        f"runtime referenced evidence outside authorized scope: {sorted(outside)}"
    )
```

Add a test where `evidence_refs=()` but one support proposal references
`fragment-outside`.

- [ ] **Step 7: Run verification/runtime tests to verify GREEN**

Run:

```bash
uv run pytest tests/core/test_verification.py tests/adapters/test_runtime.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add loop_apidoc/core/verification.py loop_apidoc/core/models.py \
  loop_apidoc/adapters/runtime.py tests/core/test_verification.py \
  tests/adapters/test_runtime.py
git commit -m "feat: verify claim support deterministically"
```

### Task 4: Relationship-Driven Reconciliation

**Files:**
- Modify: `loop_apidoc/core/reconciliation.py`
- Modify: `loop_apidoc/core/models.py`
- Rewrite focused cases in: `tests/core/test_reconciliation.py`

**Interfaces:**
- `reconcile_claims(proposals, *, evidence_bundle, previous=())
  -> tuple[GroundedClaim, ...]`
- `GroundedClaim.support_relationships:
  tuple[ClaimEvidenceRelationship, ...] = ()`
- `GroundedClaim.evidence_refs` is populated from relationships but never read for status.

- [ ] **Step 1: Replace existence-based tests with failing semantic tests**

```python
def test_document_reference_exists_but_claim_remains_unverified():
    claims = reconcile_claims(
        (_proposal("p1", True, legacy_refs=("fragment-whole",)),),
        evidence_bundle=_bundle(_whole_fragment("fragment-whole")),
    )
    assert claims[0].status is ClaimStatus.UNVERIFIED


def test_matching_support_for_every_material_path_is_supported():
    proposal, bundle = _fully_supported_operation()
    claims = reconcile_claims((proposal,), evidence_bundle=bundle)
    assert claims[0].status is ClaimStatus.SUPPORTED
    assert {
        relationship.claim_path for relationship in claims[0].support_relationships
    } == set(material_claim_paths("operation", proposal.value))


def test_partial_path_coverage_is_unverified():
    proposal, bundle = _operation_with_only_method_supported()
    claim = reconcile_claims((proposal,), evidence_bundle=bundle)[0]
    assert claim.status is ClaimStatus.UNVERIFIED
    assert any(
        item.reason_code == "CLAIM_PATH_UNCOVERED"
        for item in claim.support_relationships
    )
```

- [ ] **Step 2: Add failing merge/conflict/confidence tests**

```python
def test_multiple_fragments_supporting_same_value_merge():
    claims = reconcile_claims(
        (_supported_scalar("p1", "USD", "fragment-a"),
         _supported_scalar("p2", "USD", "fragment-b")),
        evidence_bundle=_bundle(
            _line_fragment("fragment-a", "USD"),
            _line_fragment("fragment-b", "USD"),
        ),
    )
    assert claims[0].status is ClaimStatus.SUPPORTED
    assert claims[0].evidence_refs == ("fragment-a", "fragment-b")


def test_supported_different_values_are_conflicting():
    claim = reconcile_claims(
        (_supported_scalar("p1", "USD", "fragment-a"),
         _supported_scalar("p2", "TWD", "fragment-b")),
        evidence_bundle=_bundle(
            _line_fragment("fragment-a", "USD"),
            _line_fragment("fragment-b", "TWD"),
        ),
    )[0]
    assert claim.status is ClaimStatus.CONFLICTING
    assert claim.value == ("TWD", "USD")


def test_claim_value_different_from_source_is_conflicting():
    claim = reconcile_claims(
        (_supported_scalar("p1", "USD", "fragment-a"),),
        evidence_bundle=_bundle(_line_fragment("fragment-a", "TWD")),
    )[0]
    assert claim.status is ClaimStatus.CONFLICTING
    assert any(
        item.relationship is SupportRelationshipType.CONTRADICTS
        for item in claim.support_relationships
    )


def test_runtime_confidence_does_not_change_status():
    low = _unsupported_scalar("p1", confidence=0.01)
    high = _unsupported_scalar("p2", confidence=0.99)
    claim = reconcile_claims((low, high), evidence_bundle=_bundle())[0]
    assert claim.status is ClaimStatus.UNVERIFIED
```

- [ ] **Step 3: Run reconciliation tests to verify RED**

Run:

```bash
uv run pytest tests/core/test_reconciliation.py -q
```

Expected: failures because reconciliation still accepts fragment-ID existence.

- [ ] **Step 4: Implement coverage and value reconciliation**

For each canonical identity:

```python
relationships_by_proposal = {
    proposal.id: verify_claim_support(proposal, evidence_bundle)
    for proposal in group
}
```

For each proposal, compute:

```python
required = set(material_claim_paths(proposal.claim_kind, proposal.value))
supported = {
    item.claim_path
    for item in relationships
    if item.relationship in {
        SupportRelationshipType.EXPLICIT_SUPPORT,
        SupportRelationshipType.DERIVED_SUPPORT,
    }
}
contradictions = tuple(
    item for item in relationships
    if item.relationship is SupportRelationshipType.CONTRADICTS
)
fully_supported = bool(required) and required <= supported and not contradictions
```

Create deterministic `insufficient` coverage relationships with
`reason_code="CLAIM_PATH_UNCOVERED"` for uncovered paths. Reconcile fully supported values
by canonical JSON. Any verified contradiction makes the identity conflicting, even if no
alternative runtime proposal exists.

- [ ] **Step 5: Verify old refs are compatibility output only**

Add a regression test where a proposal contains an existing exact fragment only in
`evidence_refs` and has no `support_proposals`; assert `unverified`.

- [ ] **Step 6: Run reconciliation tests to verify GREEN**

Run:

```bash
uv run pytest tests/core/test_reconciliation.py tests/core/test_verification.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add loop_apidoc/core/reconciliation.py loop_apidoc/core/models.py \
  tests/core/test_reconciliation.py
git commit -m "feat: reconcile claims from semantic support"
```

### Task 5: Service, Domain Builder, and Domain Rules

**Files:**
- Modify: `loop_apidoc/core/service.py`
- Modify: `loop_apidoc/domain/models.py`
- Modify: `loop_apidoc/domain/builder.py`
- Modify: `loop_apidoc/domain/rules.py`
- Modify: `tests/domain/test_builder.py`
- Modify: `tests/domain/test_rules.py`
- Modify: `tests/integration/test_evidence_to_release.py`

**Interfaces:**
- `ContractClaimInput(..., support_relationships=(), evidence_refs=())`
- `EvidenceBinding` adds optional relationship metadata while retaining
  fragment-ID-only parsing.
- `EvidenceToContractService.reconcile` passes `EvidenceBundle`.
- `EvidenceToContractService.build_contract` passes relationships.

- [ ] **Step 1: Write failing builder tests for field-specific bindings**

```python
def test_builder_attaches_parameter_binding_to_exact_child():
    relationship = _relationship(
        claim_identity="claim:operation:POST /payments:definition",
        claim_path="/parameters/query/amount/required",
        fragment_id="fragment-required",
        relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
    )
    contract = build_grounded_contract(
        _metadata(),
        (
            ContractClaimInput(
                identity=relationship.claim_identity,
                claim_kind="operation",
                value=_operation(required=True),
                status=ClaimStatus.SUPPORTED,
                support_relationships=(relationship,),
            ),
        ),
    )
    binding = contract.operations[0].parameters[0].evidence[0]
    assert binding.relationship_id == relationship.id
    assert binding.claim_path == relationship.claim_path


def test_fragment_id_only_binding_does_not_satisfy_semantic_rule():
    contract = _contract_with_legacy_binding_only()
    findings = ApiDomainRulePack(version="2").evaluate(contract)
    assert "CLAIM_SEMANTIC_SUPPORT_REQUIRED" in {
        finding.code for finding in findings
    }
```

- [ ] **Step 2: Write failing contradiction and coverage-rule tests**

```python
def test_supported_claim_with_incomplete_path_coverage_is_rejected_by_domain_rule():
    contract = _contract(
        claim=_claim(
            status=ClaimStatus.SUPPORTED,
            support_relationships=(_summary_relationship(),),
        )
    )
    assert "CLAIM_SUPPORT_COVERAGE_INCOMPLETE" in _codes(contract)


def test_contradiction_relationship_surfaces_domain_finding():
    contract = _contract(
        claim=_claim(
            status=ClaimStatus.CONFLICTING,
            support_relationships=(_contradiction(),),
        )
    )
    assert "CLAIM_EVIDENCE_CONTRADICTS" in _codes(contract)
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
uv run pytest tests/domain/test_builder.py tests/domain/test_rules.py \
  tests/integration/test_evidence_to_release.py -q
```

Expected: failures on missing relationship-aware models and service signature.

- [ ] **Step 4: Implement additive binding and child routing**

Define:

```python
class EvidenceBinding(FrozenModel):
    fragment_id: str
    relationship_id: str | None = None
    claim_identity: str | None = None
    claim_path: str | None = None
    relationship: SupportRelationshipType | None = None
    locator: str | None = None
```

Build bindings only from final Core relationships. Attach each binding to the aggregate
claim and route it to a parameter/response/schema-field child using the semantic claim-path
parser. Unknown paths stay on the aggregate claim and trigger coverage rules; never guess a
child.

- [ ] **Step 5: Implement semantic Domain findings**

For every claim:

```python
semantic = tuple(
    binding for binding in claim.evidence
    if binding.relationship_id is not None
)
if claim.status in {ClaimStatus.SUPPORTED, ClaimStatus.WAIVED} and not semantic:
    findings.append(_finding(
        "CLAIM_SEMANTIC_SUPPORT_REQUIRED",
        claim.identity,
        f"claims[{index}]",
        claim.identity,
    ))
```

Recompute material paths for supported claims, compare them with support-binding paths,
and emit the exact new finding codes from the design.

- [ ] **Step 6: Update service calls**

Change:

```python
claims = reconcile_claims(
    result.claim_proposals,
    evidence_bundle=bundle,
)
```

and pass `claim.support_relationships` into each `ContractClaimInput`.

- [ ] **Step 7: Run focused tests to verify GREEN**

Run:

```bash
uv run pytest tests/domain tests/core tests/integration/test_evidence_to_release.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add loop_apidoc/core/service.py loop_apidoc/domain/models.py \
  loop_apidoc/domain/builder.py loop_apidoc/domain/rules.py \
  tests/domain/test_builder.py tests/domain/test_rules.py \
  tests/integration/test_evidence_to_release.py
git commit -m "feat: preserve semantic support in contract IR"
```

### Task 6: Exact Markdown Source Facts

**Files:**
- Modify: `loop_apidoc/source_facts/models.py`
- Modify: `loop_apidoc/source_facts/markdown.py`
- Modify: `loop_apidoc/source_facts/collect.py`
- Modify: `tests/source_facts/test_markdown.py`
- Create: `tests/source_facts/test_models.py`
- Modify: `tests/source_facts/test_gate.py`
- Modify: `tests/source_facts/test_end_to_end.py`

**Interfaces:**
- Adds `TableCellFact`, `TableFact`, `PayloadFenceFact`.
- `EndpointFact` retains `line`, `parameter_names`, and `example_blocks`.
- Adds `declaration_excerpt`, `section_start_line`, `section_end_line`, `tables`, and
  `payload_fences`.
- Duplicate endpoint intersection keeps current completeness semantics and does not merge
  incompatible exact fragments into a false fact.

- [ ] **Step 1: Write failing exact-cell and declaration tests**

```python
def test_scanner_preserves_exact_table_cell_coordinates_and_content():
    endpoint = scan_markdown("doc.md", MARKDOWN_TABLE).endpoints[0]
    name_cell = endpoint.tables[0].rows[0][0]
    required_cell = endpoint.tables[0].rows[0][2]
    assert name_cell.locator == {
        "table_index": 0,
        "row_index": 0,
        "column_index": 0,
        "column_name": "Name",
    }
    assert name_cell.normalized_excerpt == "amount"
    assert name_cell.semantic_value == "amount"
    assert required_cell.normalized_excerpt == "Y"
    assert required_cell.semantic_value is True


def test_endpoint_declaration_retains_exact_line_fragment():
    endpoint = scan_markdown("doc.md", "## POST /payments\n").endpoints[0]
    assert endpoint.declaration_start_line == 1
    assert endpoint.declaration_end_line == 1
    assert endpoint.declaration_excerpt == "## POST /payments"
```

- [ ] **Step 2: Add failing conservative-token and fence tests**

```python
def test_unknown_requiredness_token_is_not_coerced():
    endpoint = scan_markdown("doc.md", TABLE_WITH_CONTEXTUAL_REQUIREDNESS).endpoints[0]
    assert endpoint.tables[0].rows[0][2].semantic_value == "conditional"


def test_payload_fence_retains_exact_lines_and_excerpt():
    endpoint = scan_markdown("doc.md", ENDPOINT_WITH_JSON_FENCE).endpoints[0]
    fence = endpoint.payload_fences[0]
    assert fence.start_line < fence.end_line
    assert fence.normalized_excerpt == '{"ok":true}'
```

- [ ] **Step 3: Run source-fact tests to verify RED**

Run:

```bash
uv run pytest tests/source_facts -q
```

Expected: failures because exact table/fence models do not exist.

- [ ] **Step 4: Implement row/cell retention without weakening scanner guards**

Keep all current table qualification rules. Change `_absorb_table` to return a
`TableFact | None` while still appending the same compatibility `parameter_names`.
Record original one-based source line numbers for every row and cell. Use the shared
`normalize_excerpt` and a versioned `_requiredness_value` with explicit token sets.

Do not infer:

- a parameter location from arbitrary prose;
- a type from a description;
- a field from a non-name-like table;
- a payload example from a pseudocode fence.

- [ ] **Step 5: Preserve duplicate-source fail-open behavior**

Update `_intersect` so compatibility fields remain the intersection, while exact table
facts remain only when canonical cell `(column_name, semantic_value)` facts exist in both
source occurrences. Ambiguous exact facts are dropped.

- [ ] **Step 6: Run source-fact tests to verify GREEN**

Run:

```bash
uv run pytest tests/source_facts tests/agentcli/test_verify_source_facts.py -q
```

Expected: PASS, including all existing issue-14 regressions.

- [ ] **Step 7: Commit**

```bash
git add loop_apidoc/source_facts tests/source_facts \
  tests/agentcli/test_verify_source_facts.py
git commit -m "feat: retain exact markdown source facts"
```

### Task 7: Fragment Acquisition Adapter

**Files:**
- Create: `loop_apidoc/adapters/fragments.py`
- Modify: `loop_apidoc/adapters/__init__.py`
- Create: `tests/adapters/test_fragments.py`
- Modify: `tests/core/test_architecture_boundaries.py`

**Interfaces:**
- `FragmentRequest(source_id, locator, parent_fragment_id=None)`
- `acquire_fragment_bundle(source_set, manifest, facts, requests, acquired_at)
  -> EvidenceBundle`
- `parse_legacy_locator(raw: str | None) -> FragmentLocator`
- Supports local Markdown, preprocessed page markers, native PDF page, JSON Pointer, and
  YAML pointer acquisition.
- URL sources without a local snapshot remain document/unresolved fragments and are never
  fetched by shadow.

- [ ] **Step 1: Write failing legacy-locator parser tests**

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("manual.pdf p.12", PageLocator(page=12)),
        ("spec.md lines 10-14", LineRangeLocator(start_line=10, end_line=14)),
        ("openapi.json#/paths/~1payments/post", JsonPointerLocator(
            pointer="/paths/~1payments/post"
        )),
        ("css:#payments", CssSelectorLocator(selector="#payments")),
        ("xpath://main/section[2]", XPathLocator(expression="//main/section[2]")),
    ],
)
def test_legacy_locator_parser_accepts_only_explicit_grammars(raw, expected):
    assert parse_legacy_locator(raw) == expected


def test_ambiguous_legacy_locator_is_unresolved():
    locator = parse_legacy_locator("see the payment section")
    assert locator.kind == "unresolved"
```

- [ ] **Step 2: Write failing Markdown and structured-source acquisition tests**

```python
def test_markdown_table_cell_fragment_hashes_only_the_cell(tmp_path):
    bundle = _acquire_markdown_table(tmp_path)
    cell = _fragment(bundle, kind="table_cell", column_name="Required")
    assert cell.normalized_excerpt == "Y"
    assert cell.fragment_digest == fragment_digest("Y")
    assert cell.parent_fragment_id is not None


def test_json_pointer_fragment_uses_canonical_selected_value(tmp_path):
    bundle = _acquire_json(
        tmp_path,
        {"components": {"schemas": {"Id": {"type": "string"}}}},
        pointer="/components/schemas/Id",
    )
    fragment = _only_exact(bundle)
    assert fragment.semantic_value == {"type": "string"}
    assert fragment.normalized_excerpt == '{"type":"string"}'


def test_url_without_local_snapshot_is_never_fetched(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: pytest.fail("network used"))
    bundle = _acquire_url_without_snapshot()
    assert all(
        fragment.precision is not FragmentPrecision.EXACT
        for fragment in bundle.fragments
    )
```

- [ ] **Step 3: Write failing PDF page and parent/child tests**

Create a two-page PDF fixture with PyMuPDF inside the test. Request page 2 and assert the
fragment excerpt contains only page 2 text, its digest differs from the artifact digest,
and its parent is the document fragment.

- [ ] **Step 4: Run adapter tests to verify RED**

Run:

```bash
uv run pytest tests/adapters/test_fragments.py -q
```

Expected: import failure for `adapters.fragments`.

- [ ] **Step 5: Implement acquisition without semantic decisions**

The adapter:

1. reads each local source once;
2. hashes original bytes for `SourceArtifact.content_digest`;
3. creates a document parent fragment;
4. resolves only typed fragment requests and enriched source facts;
5. normalizes and hashes the selected content;
6. records `semantic_value` only from deterministic parsing;
7. returns unresolved/document fragments for unsupported requests;
8. never calls network or a runtime.

Resolve JSON Pointers with RFC 6901 decoding:

```python
def _resolve_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise FragmentAcquisitionError("JSON Pointer must be empty or start with '/'")
    current = value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current
```

- [ ] **Step 6: Extend architecture tests**

Add AST tests that Core and Domain do not:

- import `os`, `io`, `socket`, `urllib`, `pymupdf`, `fitz`, or database/model packages;
- call `open`, `Path.read_*`, `Path.write_*`, `socket`, or HTTP clients;
- directly call model/runtime adapters.

The test itself may use `pathlib` to inspect source, as it does today.

- [ ] **Step 7: Run adapter and boundary tests to verify GREEN**

Run:

```bash
uv run pytest tests/adapters/test_fragments.py \
  tests/core/test_architecture_boundaries.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add loop_apidoc/adapters/fragments.py loop_apidoc/adapters/__init__.py \
  tests/adapters/test_fragments.py tests/core/test_architecture_boundaries.py
git commit -m "feat: acquire exact source fragments"
```

### Task 8: Shadow Bridge Migration and Degradation

**Files:**
- Modify: `loop_apidoc/shadow/bridge.py`
- Modify: `loop_apidoc/shadow/models.py`
- Modify: `loop_apidoc/shadow/runner.py`
- Modify: `tests/shadow/test_bridge_sources.py`
- Modify: `tests/shadow/test_bridge_claims.py`
- Modify: `tests/shadow/test_runner.py`

**Interfaces:**
- `build_evidence` accepts adapter-materialized fragments instead of inventing support from
  manifest digests.
- `build_source_set(manifest, generated_at) -> BridgeSourceInputs` remains pure and runs
  before `acquire_fragment_bundle`; `build_evidence` then combines that source set with the
  adapter-produced artifacts/fragments.
- `build_runtime_result` emits `support_proposals`, retaining `evidence_refs` only for
  compatibility serialization.
- `execute_shadow` accepts `sources_root` and enriched `FactIndex`.
- Bridge diagnostics add:
  `LEGACY_CITATION_DEGRADED`,
  `LOCATOR_UNRESOLVED`,
  `FRAGMENT_NOT_MATERIALIZED`,
  `CLAIM_PATH_UNSUPPORTED`.

- [ ] **Step 1: Rewrite whole-source shadow expectation as failing degradation test**

```python
def test_filename_only_legacy_citation_is_not_supported():
    plan = _plan(endpoints=[_endpoint(source="manual.md")])
    artifacts = execute_shadow(
        manifest=_manifest(),
        plan=plan,
        facts=FactIndex(),
        sources_root=_sources_root(),
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )
    assert artifacts.claims[0].status is ClaimStatus.UNVERIFIED
    assert any(
        item.code == "LEGACY_CITATION_DEGRADED"
        for item in artifacts.comparison.diagnostics
    )
```

- [ ] **Step 2: Add failing exact-table support and contradiction tests**

```python
def test_shadow_table_cell_supports_matching_parameter_field():
    artifacts = _execute_markdown_table_shadow(required=True, source_required="Y")
    claim = _operation_claim(artifacts)
    assert any(
        relationship.claim_path == "/parameters/query/amount/required"
        and relationship.relationship is SupportRelationshipType.EXPLICIT_SUPPORT
        for relationship in claim.support_relationships
    )


def test_shadow_table_cell_mismatch_is_conflicting():
    artifacts = _execute_markdown_table_shadow(required=False, source_required="Y")
    claim = _operation_claim(artifacts)
    assert claim.status is ClaimStatus.CONFLICTING
    assert any(
        relationship.relationship is SupportRelationshipType.CONTRADICTS
        for relationship in claim.support_relationships
    )
```

- [ ] **Step 3: Add failing precise-line and JSON Pointer bridge tests**

Assert that:

- `manual.md lines 4-4` creates a `LineRangeLocator` exact fragment;
- `openapi.json#/paths/~1payments/post/summary` creates a structured fragment;
- a materialized exact matching scalar emits `ClaimSupportProposal`;
- an unresolved citation emits only an insufficient proposal/diagnostic.

- [ ] **Step 4: Run shadow bridge tests to verify RED**

Run:

```bash
uv run pytest tests/shadow/test_bridge_sources.py \
  tests/shadow/test_bridge_claims.py tests/shadow/test_runner.py -q
```

Expected: failures because shadow still resolves citations to whole fragments.

- [ ] **Step 5: Implement conservative citation-to-fragment mapping**

For every material claim path:

1. inspect exact fragments associated with each legacy citation;
2. prefer a source-fact cell whose semantic field identity matches the claim path;
3. otherwise use an explicit line/page/section/pointer fragment only when the verifier is
   applicable;
4. emit a support proposal naming the exact verifier;
5. if no exact fragment exists, emit a legacy-reference support proposal that Core
   classifies insufficient and record a diagnostic.

Do not copy `PlanItemStatus.SUPPORTED` into Core claim status.

- [ ] **Step 6: Preserve deterministic proposal IDs**

Include sorted support-proposal canonical payloads, not deprecated `evidence_refs`, in the
stable proposal-ID input. Two equivalent plans and evidence bundles must produce identical
runtime results independent of source/fact ordering.

- [ ] **Step 7: Run shadow tests to verify GREEN**

Run:

```bash
uv run pytest tests/shadow/test_bridge_sources.py \
  tests/shadow/test_bridge_claims.py tests/shadow/test_runner.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add loop_apidoc/shadow/bridge.py loop_apidoc/shadow/models.py \
  loop_apidoc/shadow/runner.py tests/shadow/test_bridge_sources.py \
  tests/shadow/test_bridge_claims.py tests/shadow/test_runner.py
git commit -m "feat: bridge legacy citations to semantic support"
```

### Task 9: Evidence-Aware OpenAPI, Review, and Provenance Projections

**Files:**
- Modify: `loop_apidoc/domain/projections.py`
- Modify: `loop_apidoc/core/service.py`
- Modify: `loop_apidoc/core/ports.py` if projection storage typing changes
- Modify: `tests/domain/test_projections.py`
- Modify: `tests/integration/test_evidence_to_release.py`

**Interfaces:**
- Adds `ProjectionInput(contract, source_set, evidence)`.
- Existing `compiler.compile(contract)` remains valid.
- Adds `ProvenanceProjectionCompiler(version: str)`.
- `OpenApiProjectionCompiler` emits `x-loop-claim-map`.
- `ReviewProjectionCompiler` emits relationship/fragment/artifact trace summaries.

- [ ] **Step 1: Write failing field-level provenance test**

```python
def test_operation_fields_trace_to_different_exact_fragments():
    projection = ProvenanceProjectionCompiler(version="1").compile(
        _projection_input_with_split_operation_evidence()
    )
    payload = json.loads(projection.content)
    by_target = {entry["target"]: entry for entry in payload["entries"]}
    assert (
        by_target["paths./payments.post.summary"]["fragment_id"]
        == "fragment-summary"
    )
    assert (
        by_target["paths./payments.post.parameters.query.amount.required"][
            "fragment_id"
        ]
        == "fragment-required"
    )
    assert by_target["paths./payments.post.summary"]["source_artifact_id"] != (
        by_target["paths./payments.post.parameters.query.amount.required"][
            "source_artifact_id"
        ]
    )
```

- [ ] **Step 2: Write failing OpenAPI/review trace tests**

```python
def test_openapi_claim_map_joins_field_target_to_claim_path():
    payload = json.loads(
        OpenApiProjectionCompiler(version="2")
        .compile(_projection_input_with_split_operation_evidence())
        .content
    )
    mapping = payload["paths"]["/payments"]["post"]["x-loop-claim-map"]
    assert mapping["/summary"]["claim_path"] == "/summary"


def test_review_projection_contains_relationship_and_exact_locator():
    payload = json.loads(
        ReviewProjectionCompiler(version="2")
        .compile(_projection_input_with_split_operation_evidence())
        .content
    )
    assert payload["relationships"][0]["fragment_locator"]["kind"] != "whole_document"
```

- [ ] **Step 3: Run projection tests to verify RED**

Run:

```bash
uv run pytest tests/domain/test_projections.py -q
```

Expected: failures because projection compilers accept only contracts and no provenance
compiler exists.

- [ ] **Step 4: Implement backward-compatible projection input normalization**

```python
def _projection_input(value: GroundedApiContract | ProjectionInput) -> ProjectionInput:
    if isinstance(value, ProjectionInput):
        return value
    return ProjectionInput(contract=value)
```

Evidence-aware compilers require `source_set` and `evidence`; if absent, OpenAPI preserves
current output, review preserves current contract serialization, and provenance emits no
trace entries rather than inventing source data.

- [ ] **Step 5: Implement exact target mapping**

Add pure mapping functions from `(claim_kind, claim_path, canonical value)` to exact
OpenAPI targets. Reject unknown paths from provenance with an explicit trace diagnostic;
never collapse them to the operation target.

Join:

```text
relationship.fragment_id
→ EvidenceFragment.source_artifact_id
→ SourceArtifact.source_id
→ SourceDescriptor.locator
```

Sort entries by target, claim identity, claim path, relationship ID, and fragment ID.

- [ ] **Step 6: Pass evidence into service projection compilation**

In `EvidenceToContractService.validate`, retrieve the bundle and call:

```python
projection_input = ProjectionInput(
    contract=contract,
    source_set=self.evidence_store.get_source_set(source_set_id),
    evidence=self.evidence_store.get_bundle(source_set_id),
)
projections = tuple(compiler.compile(projection_input) for compiler in compilers)
```

- [ ] **Step 7: Run projection and release tests to verify GREEN**

Run:

```bash
uv run pytest tests/domain/test_projections.py \
  tests/integration/test_evidence_to_release.py tests/adapters/test_local.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add loop_apidoc/domain/projections.py loop_apidoc/core/service.py \
  loop_apidoc/core/ports.py tests/domain/test_projections.py \
  tests/integration/test_evidence_to_release.py
git commit -m "feat: project claim-level evidence provenance"
```

### Task 10: Shadow Artifacts and Safe Failure Isolation

**Files:**
- Modify: `loop_apidoc/shadow/models.py`
- Modify: `loop_apidoc/shadow/runner.py`
- Modify: `loop_apidoc/shadow/report.py`
- Modify: `loop_apidoc/agentcli/assemble.py`
- Modify: `tests/shadow/test_models.py`
- Modify: `tests/shadow/test_report.py`
- Modify: `tests/agentcli/test_assemble.py`
- Modify: `tests/test_cli_assemble.py`

**Interfaces:**
- Successful shadow output adds `relationships.json` and `projections/`.
- `run_shadow_safely` accepts `sources_root` and `facts`.
- `ShadowStage` adds `ACQUISITION`, `VERIFICATION`, and `PROJECTION`.
- Existing `ShadowExecutionSummary` and CLI JSON remain additive.

- [ ] **Step 1: Write failing successful-artifact test**

```python
EXPECTED_FILES = {
    "source-set.json",
    "evidence.json",
    "runtime-result.json",
    "relationships.json",
    "claims.json",
    "contract.json",
    "decision.json",
    "workflow.json",
    "events.json",
    "comparison.json",
    "projections",
}


def test_report_writes_relationships_and_three_projections(tmp_path):
    summary = write_shadow_artifacts(_artifacts(), tmp_path / "core")
    assert summary.status == "ok"
    assert {path.name for path in (tmp_path / "core").iterdir()} == EXPECTED_FILES
    assert {
        path.name for path in (tmp_path / "core" / "projections").iterdir()
    } == {"openapi.json", "review-data.json", "provenance.json"}
```

- [ ] **Step 2: Write failing failure-isolation matrix**

Parameterize acquisition, bridge, verification, service, projection, comparison, and
report failures. For each injected exception, assert:

```python
assert result.status is expected_legacy_status
assert result.report == expected_legacy_report
assert result.shadow.status == "error"
assert cli_exit_code == (0 if expected_legacy_report.ok else 1)
assert score_calls == expected_score_calls
assert foundry_calls == 0
assert approval_calls == 0
```

Also retain the default-mode assertion that no `core/` directory exists.

- [ ] **Step 3: Run shadow/assemble tests to verify RED**

Run:

```bash
uv run pytest tests/shadow/test_report.py tests/agentcli/test_assemble.py \
  tests/test_cli_assemble.py -q
```

Expected: failures on new artifacts/stages/signatures.

- [ ] **Step 4: Compile observational projections in shadow runner**

Call service validation with:

```python
(
    OpenApiProjectionCompiler(version="2"),
    ReviewProjectionCompiler(version="2"),
    ProvenanceProjectionCompiler(version="1"),
)
```

Store projections and the flattened sorted relationship tuple in `ShadowArtifacts`.
Never call `approve`, `publish`, Foundry, or legacy generators from the Core path.

- [ ] **Step 5: Write artifacts atomically**

Keep the existing staging-directory replacement. Write all root JSON and projection files
inside staging. On any failure, delete staging and leave only `core/error.json`.

- [ ] **Step 6: Reuse facts collected before the extraction gate**

In `run_assemble_pipeline`:

```python
facts = collect_facts(sources_root, manifest)
violations = check_extraction(
    inventory,
    named_endpoints(extraction_dir, endpoint_texts),
    integration,
    manifest,
    facts,
)
```

Pass the same `facts` and `sources_root` to `run_shadow_safely`; do not read Markdown twice
for facts.

- [ ] **Step 7: Run shadow/assemble tests to verify GREEN**

Run:

```bash
uv run pytest tests/shadow tests/agentcli/test_assemble.py \
  tests/test_cli_assemble.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add loop_apidoc/shadow loop_apidoc/agentcli/assemble.py \
  tests/shadow tests/agentcli/test_assemble.py tests/test_cli_assemble.py
git commit -m "feat: publish semantic support shadow artifacts"
```

### Task 11: Evaluation Metrics and Compatibility Regressions

**Files:**
- Modify: `loop_apidoc/evaluation/models.py`
- Modify: `loop_apidoc/evaluation/metrics.py`
- Modify: `loop_apidoc/evaluation/replay.py`
- Modify: `tests/evaluation/test_metrics.py`
- Modify: `tests/evaluation/test_replay.py`
- Modify: `tests/adapters/test_memory.py`
- Modify: `tests/shadow/test_models.py`

**Interfaces:**
- `ExpectedRelationship` records claim identity/path, fragment, and relationship.
- `MetricReport` adds:
  `semantic_support_precision`,
  `semantic_support_recall`,
  `claim_path_coverage`,
  `contradiction_detection_recall`.
- Evaluation remains unable to approve or mutate production assets.

- [ ] **Step 1: Write failing semantic metric tests**

```python
def test_relationship_metrics_distinguish_reference_from_support():
    expected = (_expected_support("/summary", "fragment-summary"),)
    observed = (_expected_insufficient("/summary", "fragment-summary"),)
    report = evaluate_relationships(expected, observed)
    assert report.semantic_support_precision == 0.0
    assert report.semantic_support_recall == 0.0
    assert report.claim_path_coverage == 0.0


def test_contradiction_detection_recall_counts_exact_mismatch():
    report = evaluate_relationships(
        (_expected_contradiction("fragment-a"),),
        (_expected_contradiction("fragment-a"),),
    )
    assert report.contradiction_detection_recall == 1.0
```

- [ ] **Step 2: Run evaluation tests to verify RED**

Run:

```bash
uv run pytest tests/evaluation -q
```

Expected: missing expected-relationship models and metrics.

- [ ] **Step 3: Implement relationship-keyed metrics**

Use canonical keys:

```python
(claim_identity, claim_path, fragment_id, relationship.value)
```

Do not count `insufficient` as semantic support. Preserve old claim/evidence-reference
metrics for compatibility, but document that they measure runtime proposal quality rather
than Core truth.

- [ ] **Step 4: Update replay without adding mutation ports**

Replay may call `verify_claim_support` only when the evaluation case supplies an immutable
evidence bundle. Keep constructor parameters exactly `runtime` and `domain_pack`; cases
carry evidence as data.

- [ ] **Step 5: Run evaluation/adapter tests to verify GREEN**

Run:

```bash
uv run pytest tests/evaluation tests/adapters/test_memory.py \
  tests/shadow/test_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add loop_apidoc/evaluation tests/evaluation \
  tests/adapters/test_memory.py tests/shadow/test_models.py
git commit -m "feat: evaluate semantic evidence support"
```

### Task 12: Teaching, Promotion, Skill, and Agent Documentation

**Files:**
- Modify: `README.en.md`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/index.html`
- Modify: `docs/index.en.html`
- Modify: `docs/introduction.html`
- Modify: `docs/introduction.en.html`
- Modify: `docs/onboarding.en.html`
- Modify: `docs/onboarding.html`
- Modify: `docs/operator-manual.en.html`
- Modify: `docs/operator-manual.html`
- Modify: `docs/architecture-manual.en.html`
- Modify: `docs/architecture-manual.html`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `skills/loop-apidoc/SKILL.md`
- Modify: `skills/loop-apidoc/reference/extraction-schemas.md`
- Modify: `skills/loop-apidoc/reference/assemble-and-correction.md`
- Modify: `tests/docs/test_model_independent_architecture.py`
- Modify: `tests/docs/test_core_shadow_documentation.py`

**Interfaces:**
- English is canonical teaching/promotion copy; zh-TW is the synchronized supporting
  layer.
- Documentation describes exact fragments, relationships, deterministic support, degraded
  legacy citations, new shadow artifacts, and unchanged legacy authority.

- [ ] **Step 1: Write failing documentation contract tests**

```python
@pytest.mark.parametrize("path", [
    "README.en.md",
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/operator-manual.en.html",
    "docs/operator-manual.html",
])
def test_shadow_docs_explain_semantic_support_and_degraded_legacy_refs(path):
    text = Path(path).read_text(encoding="utf-8")
    assert "explicit_support" in text
    assert "insufficient" in text
    assert "relationships.json" in text
    assert "legacy" in text.lower()


def test_agent_guides_keep_file_io_inventory_aligned():
    for path in ("AGENTS.md", "CLAUDE.md"):
        text = Path(path).read_text(encoding="utf-8")
        assert "adapters/fragments.py" in text
        assert "shadow/report.py" in text
```

- [ ] **Step 2: Run docs tests to verify RED**

Run:

```bash
uv run pytest tests/docs/test_model_independent_architecture.py \
  tests/docs/test_core_shadow_documentation.py -q
```

Expected: failures because the documents still describe whole-source fragments.

- [ ] **Step 3: Update canonical English documentation**

Document:

- the claim → relationship → fragment → artifact chain;
- typed locator and fragment digest semantics;
- deterministic verifiers and their limits;
- new `core/relationships.json` and `core/projections/`;
- whole-document legacy citations becoming insufficient/unverified;
- shadow's non-authoritative status;
- `adapters/fragments.py` as a read-side I/O exit.

- [ ] **Step 4: Synchronize Traditional Chinese documentation**

Translate the same behavior without changing commands, file names, enums, or authority
semantics. Keep `AGENTS.md` and `CLAUDE.md` substantively identical.

- [ ] **Step 5: Update extraction skill contracts**

Require citation strings to prefer the explicit accepted grammars from the design. State
that a filename-only source remains valid for legacy validation compatibility but degrades
in semantic shadow. Do not require new extraction JSON keys in this phase.

- [ ] **Step 6: Run documentation tests to verify GREEN**

Run:

```bash
uv run pytest tests/docs tests/test_plugin_manifest.py \
  tests/test_loop_sdk_author_skill.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add README.en.md README.md docs AGENTS.md CLAUDE.md \
  skills/loop-apidoc tests/docs tests/test_plugin_manifest.py \
  tests/test_loop_sdk_author_skill.py
git commit -m "docs: explain claim-level semantic evidence"
```

### Task 13: Full Verification and Release-Readiness Evidence

**Files:**
- Modify only if a verification failure exposes a defect in files already in scope.
- Update execution record in:
  `docs/superpowers/plans/2026-07-20-claim-level-semantic-support.md`
  after all checks pass.

**Interfaces:**
- Produces final test, coverage, lint, architecture, compatibility, and diff-check evidence.

- [ ] **Step 1: Run the complete focused acceptance matrix**

```bash
uv run pytest tests/domain tests/core tests/adapters tests/source_facts \
  tests/shadow tests/agentcli/test_assemble.py tests/test_cli_assemble.py \
  tests/generate tests/integration tests/evaluation -q
```

Expected: PASS.

- [ ] **Step 2: Run Ruff**

```bash
uv run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 3: Run the full suite with coverage**

```bash
uv run pytest --cov=loop_apidoc
```

Expected:

- all non-source-dependent tests pass;
- benchmark cases without local sources may skip under the documented policy;
- total coverage is at least 95.00%;
- no coverage fail-under error.

- [ ] **Step 4: Run project quality and diff checks**

```bash
uv run python scripts/quality_gate.py
git diff --check
git status --short
```

Expected:

- quality gate passes in CI-safe mode;
- `git diff --check` emits no output;
- status lists only intentional files.

- [ ] **Step 5: Inspect one shadow artifact chain**

Run one representative shadow assemble fixture and verify:

```text
OpenAPI x-loop-claim-map target
→ core/projections/provenance.json claim identity/path
→ core/relationships.json relationship
→ core/evidence.json exact fragment and parent
→ core/evidence.json source artifact
→ core/source-set.json logical source locator
```

Confirm a filename-only citation is `insufficient/unverified` in the same run.

- [ ] **Step 6: Record exact verification results**

Append an execution record below the plan header with:

- passed/skipped test counts;
- total coverage percentage;
- Ruff result;
- quality-gate result;
- architecture-boundary result;
- shadow failure-isolation result.

- [ ] **Step 7: Commit the verification record**

If Step 1–5 exposes a defect, return to the owning task's red/green cycle and use that
task's exact file/commit list first. After every check is green, commit the execution
record:

```bash
git add docs/superpowers/plans/2026-07-20-claim-level-semantic-support.md
git commit -m "docs: record semantic evidence verification"
```

---

## Implementation Completion Criteria

Implementation is complete only when:

1. every required acceptance scenario has a red-before-green test history;
2. Core never treats evidence-ID existence as support;
3. claim path coverage gates `supported`;
4. contradictions deterministically produce `conflicting`;
5. same-value support merges and different-value support conflicts;
6. exact fragment digests/locators/IDs/relationships are deterministic;
7. old whole-document citations degrade explicitly;
8. observational provenance traces field → claim → relationship → exact fragment →
   artifact → source;
9. shadow failure leaves every legacy authority and exit behavior unchanged;
10. Core/Domain boundary tests prohibit direct I/O/platform/model dependencies;
11. teaching/promotion/skill/agent documentation is synchronized;
12. Ruff passes and total coverage is at least 95%.
