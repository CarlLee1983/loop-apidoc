# Model-Independent loop-apidoc Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add an executable, model-independent evidence-to-contract architecture alongside the existing agent-native CLI without changing its current behavior.

**Architecture:** Introduce four inward-facing packages: `domain` owns canonical API contract semantics and deterministic projections/rules; `core` owns immutable evidence, claim reconciliation, lifecycle, policy, governance, ports, and use cases; `adapters` provides replaceable in-memory and local reference implementations; `evaluation` replays immutable cases without production-state access. Existing CLI modules remain compatibility adapters and are not migrated in this change.

**Tech Stack:** Python 3.11+, Pydantic v2 immutable models, standard-library protocols and hashing, pytest, Ruff.

## Global Constraints

- Product Core and Domain must not import a model vendor, agent framework, transport, storage engine, interface, or deployment platform.
- Source material is the only factual authority; unsupported proposals stay `unverified`.
- Runtime confidence is diagnostic metadata and never decides claim status.
- OpenAPI and review data are deterministic projections, not canonical truth.
- Generation, approval, and publication remain separate lifecycle transitions.
- Runtime identity is recorded but is not part of contract identity.
- The current agent-native CLI and its artifact formats remain backward compatible.

---

### Task 1: Canonical API Domain Pack

**Files:**
- Create: `loop_apidoc/domain/__init__.py`
- Create: `loop_apidoc/domain/models.py`
- Create: `loop_apidoc/domain/identity.py`
- Create: `loop_apidoc/domain/rules.py`
- Create: `loop_apidoc/domain/projections.py`
- Test: `tests/domain/test_identity.py`
- Test: `tests/domain/test_rules.py`
- Test: `tests/domain/test_projections.py`

**Interfaces:**
- Consumes: no Core, adapter, CLI, filesystem, or runtime types.
- Produces: immutable `GroundedApiContract`, API ontology value types, canonical identity functions, `ApiDomainRulePack.evaluate(contract)`, and `ProjectionCompiler.compile(contract)`.

- [x] **Step 1: Write identity and immutable-IR tests**

```python
def test_operation_identity_is_stable_across_method_case():
    assert canonical_operation_identity("post", "/payments") == "operation:POST:/payments"

def test_contract_is_immutable():
    contract = GroundedApiContract(metadata=ContractMetadata(...))
    with pytest.raises(ValidationError):
        contract.operations = ()
```

- [x] **Step 2: Run identity tests and confirm missing-module failures**

Run: `uv run pytest tests/domain/test_identity.py -q`

Expected: FAIL because `loop_apidoc.domain` does not exist.

- [x] **Step 3: Implement ontology, IR, and canonical identity functions**

Define frozen, extra-forbidden Pydantic models for metadata, evidence bindings, environments,
operations, webhooks, schemas and fields, security, errors, integration mechanics,
operational constraints, gaps, conflicts, and waivers. Identity functions normalize only
syntax explicitly allowed by the ontology and raise `DomainIdentityError` for invalid input.

- [x] **Step 4: Run identity tests**

Run: `uv run pytest tests/domain/test_identity.py -q`

Expected: PASS.

- [x] **Step 5: Write deterministic-rule tests**

```python
def test_rules_report_dangling_schema_and_missing_evidence():
    findings = ApiDomainRulePack(version="1").evaluate(contract)
    assert {finding.code for finding in findings} == {
        "CLAIM_EVIDENCE_REQUIRED",
        "SCHEMA_REFERENCE_UNRESOLVED",
    }
```

- [x] **Step 6: Run rule tests and confirm missing-rule failures**

Run: `uv run pytest tests/domain/test_rules.py -q`

Expected: FAIL because `ApiDomainRulePack` is not implemented.

- [x] **Step 7: Implement versioned deterministic rule contracts**

Implement typed findings and deterministic checks for operation identity, path/method
legality, response completeness, schema/security/server/reference resolution, callback and
cryptographic completeness, conditional requiredness, integration cross-references,
error applicability, and accepted-claim evidence bindings.

- [x] **Step 8: Run rule tests**

Run: `uv run pytest tests/domain/test_rules.py -q`

Expected: PASS.

- [x] **Step 9: Write projection tests**

```python
def test_openapi_projection_is_reproducible_and_preserves_no_core_state():
    compiler = OpenApiProjectionCompiler(version="1")
    first = compiler.compile(contract)
    second = compiler.compile(contract)
    assert first == second
    assert first.media_type == "application/vnd.oai.openapi+json;version=3.1"
```

- [x] **Step 10: Run projection tests and confirm missing-compiler failures**

Run: `uv run pytest tests/domain/test_projections.py -q`

Expected: FAIL because projection compilers are not implemented.

- [x] **Step 11: Implement projection contracts and reference compilers**

Implement a generic `Projection` value, `ProjectionCompiler` protocol,
`OpenApiProjectionCompiler`, and `ReviewProjectionCompiler`. Compilers return immutable
artifact values and perform no I/O.

- [x] **Step 12: Run Domain tests**

Run: `uv run pytest tests/domain -q`

Expected: PASS.

### Task 2: Evidence and Product Core

**Files:**
- Create: `loop_apidoc/core/__init__.py`
- Create: `loop_apidoc/core/models.py`
- Create: `loop_apidoc/core/ports.py`
- Create: `loop_apidoc/core/reconciliation.py`
- Create: `loop_apidoc/core/lifecycle.py`
- Create: `loop_apidoc/core/policy.py`
- Create: `loop_apidoc/core/governance.py`
- Create: `loop_apidoc/core/service.py`
- Test: `tests/core/test_reconciliation.py`
- Test: `tests/core/test_lifecycle.py`
- Test: `tests/core/test_policy.py`
- Test: `tests/core/test_governance.py`
- Test: `tests/core/test_architecture_boundaries.py`

**Interfaces:**
- Consumes: Domain identity, contract, rule, and projection contracts.
- Produces: evidence and runtime work/result values, all Core port protocols,
  `reconcile_claims`, `LifecycleMachine`, `ValidationPolicyEngine`,
  governed releases, and `EvidenceToContractService`.

- [x] **Step 1: Write claim-reconciliation tests**

```python
def test_runtime_consensus_without_valid_evidence_remains_unverified():
    claims = reconcile_claims(two_matching_proposals, evidence_fragment_ids=set())
    assert claims[0].status is ClaimStatus.UNVERIFIED

def test_incompatible_supported_values_are_conflicting():
    claims = reconcile_claims(proposals, evidence_fragment_ids={"fragment-a", "fragment-b"})
    assert claims[0].status is ClaimStatus.CONFLICTING
```

- [x] **Step 2: Run reconciliation tests and confirm missing-module failures**

Run: `uv run pytest tests/core/test_reconciliation.py -q`

Expected: FAIL because `loop_apidoc.core` does not exist.

- [x] **Step 3: Implement immutable evidence/runtime/claim models, ports, and reconciliation**

Model source sets, source artifacts, evidence fragments/bundles, claim proposals, grounded
claims, extraction work items/results, actor identities, events, findings, corrections,
decisions, releases, and workflow records. Reconciliation validates every evidence reference,
deduplicates values canonically, merges valid support, preserves conflicts, and supersedes
older identities deterministically.

- [x] **Step 4: Run reconciliation tests**

Run: `uv run pytest tests/core/test_reconciliation.py -q`

Expected: PASS.

- [x] **Step 5: Write lifecycle and policy tests**

```python
def test_publish_cannot_skip_approval():
    with pytest.raises(InvalidTransition):
        machine.transition(validated, LifecycleState.PUBLISHED, actor=publisher)

def test_policy_verdict_ignores_runtime_confidence():
    low = engine.decide(findings, runtime_confidence=0.01)
    high = engine.decide(findings, runtime_confidence=0.99)
    assert low.verdict == high.verdict
```

- [x] **Step 6: Run lifecycle/policy tests and confirm feature failures**

Run: `uv run pytest tests/core/test_lifecycle.py tests/core/test_policy.py -q`

Expected: FAIL because transition and policy behavior is not implemented.

- [x] **Step 7: Implement lifecycle and policy engine**

Implement the canonical transition graph with artifact guards, actor guards, idempotency
keys, invalidation transitions, append-only events, named policy severity overrides,
deterministic verdicts, root-cause grouping, typed correction requests, and scoped,
time-bounded waiver application.

- [x] **Step 8: Run lifecycle/policy tests**

Run: `uv run pytest tests/core/test_lifecycle.py tests/core/test_policy.py -q`

Expected: PASS.

- [x] **Step 9: Write governance, use-case, and boundary tests**

```python
def test_runtime_cannot_approve_its_own_release():
    with pytest.raises(ApprovalRejected):
        approve_release(candidate, decision_from_same_runtime)

def test_core_and_domain_do_not_import_platform_packages():
    assert forbidden_imports("loop_apidoc/core") == set()
    assert forbidden_imports("loop_apidoc/domain") == set()
```

- [x] **Step 10: Run governance/boundary tests and confirm failures**

Run: `uv run pytest tests/core/test_governance.py tests/core/test_architecture_boundaries.py -q`

Expected: FAIL until governance, use cases, and boundary compliance exist.

- [x] **Step 11: Implement governance and intent-oriented use cases**

Implement immutable candidate/approved/published/stale/superseded/revoked releases,
content-derived release identities, current pointers, approval separation, and an
`EvidenceToContractService` that registers, acquires, requests proposals, reconciles, builds,
validates, approves, and publishes exclusively through ports.

- [x] **Step 12: Run Core tests**

Run: `uv run pytest tests/core -q`

Expected: PASS.

### Task 3: Reference Adapter Ecosystem

**Files:**
- Create: `loop_apidoc/adapters/__init__.py`
- Create: `loop_apidoc/adapters/memory.py`
- Create: `loop_apidoc/adapters/local.py`
- Create: `loop_apidoc/adapters/runtime.py`
- Test: `tests/adapters/test_memory.py`
- Test: `tests/adapters/test_local.py`
- Test: `tests/adapters/test_runtime.py`
- Test: `tests/integration/test_evidence_to_release.py`

**Interfaces:**
- Consumes: Core port protocols and immutable Core/Domain values.
- Produces: in-memory stores/sinks, local-file source and directory artifact adapters,
  callable runtime adapter, fixed/system clocks, static approval adapter.

- [x] **Step 1: Write adapter conformance and trust-boundary tests**

```python
def test_local_source_hashes_original_and_normalized_fragments(tmp_path):
    bundle = LocalFileSourceAdapter().acquire(source_set)
    assert bundle.artifacts[0].content_digest == sha256(source_bytes)
    assert bundle.fragments[0].source_artifact_id == bundle.artifacts[0].id

def test_runtime_adapter_rejects_out_of_scope_evidence():
    with pytest.raises(RuntimeContractError):
        adapter.propose(work_item)
```

- [x] **Step 2: Run adapter tests and confirm missing-module failures**

Run: `uv run pytest tests/adapters -q`

Expected: FAIL because reference adapters do not exist.

- [x] **Step 3: Implement reference adapters**

Implement replaceable adapters only in the outer package. Local source acquisition reads
authorized files and hashes immutable content; directory publication writes already-compiled
projection bytes; in-memory repositories enforce immutability; the runtime adapter validates
scope, diagnostics, telemetry, and evidence references; approval adapters return typed
decisions without mutating Core.

- [x] **Step 4: Run adapter tests**

Run: `uv run pytest tests/adapters -q`

Expected: PASS.

- [x] **Step 5: Write an end-to-end in-memory evidence-to-release test**

```python
def test_source_to_published_release_is_a_governed_sequence():
    service.register_source_set(source_set)
    service.acquire(source_set.id)
    service.request_claim_proposals(source_set.id, requested_claim_kinds=("operation",))
    service.reconcile(source_set.id)
    service.build_contract(source_set.id)
    decision = service.validate(source_set.id, compilers)
    service.approve(source_set.id)
    release = service.publish(source_set.id)
    assert release.status is ReleaseStatus.PUBLISHED
    assert artifact_sink.publications
```

- [x] **Step 6: Run the end-to-end test and fix only contract-integration defects**

Run: `uv run pytest tests/integration/test_evidence_to_release.py -q`

Expected: PASS after adapter and Core contracts align.

### Task 4: Isolated Evaluation System

**Files:**
- Create: `loop_apidoc/evaluation/__init__.py`
- Create: `loop_apidoc/evaluation/models.py`
- Create: `loop_apidoc/evaluation/metrics.py`
- Create: `loop_apidoc/evaluation/replay.py`
- Test: `tests/evaluation/test_metrics.py`
- Test: `tests/evaluation/test_replay.py`

**Interfaces:**
- Consumes: immutable evidence bundles, work items, Runtime Port, Domain Pack, and expected
  claim/projection signatures.
- Produces: versioned evaluation cases, metric reports, replay reports, and comparison values;
  accepts no production store or publication port.

- [x] **Step 1: Write metric and isolation tests**

```python
def test_claim_precision_and_recall_are_independent_of_production_verdict():
    report = evaluate_claims(expected, observed)
    assert report.claim_precision == 0.5
    assert report.claim_recall == 1.0

def test_replay_runner_constructor_has_no_production_mutation_ports():
    assert set(inspect.signature(ReplayRunner).parameters) == {"runtime", "domain_pack"}
```

- [x] **Step 2: Run evaluation tests and confirm missing-module failures**

Run: `uv run pytest tests/evaluation -q`

Expected: FAIL because the evaluation package does not exist.

- [x] **Step 3: Implement versioned cases, metrics, replay, and comparison**

Implement immutable datasets and deterministic metrics for claim precision/recall, missing
facts, conflicts, evidence-reference correctness, unsupported assertions, cost, latency, and
cross-run stability. Replay invokes only public runtime/domain contracts and returns reports
without writing or approving assets.

- [x] **Step 4: Run evaluation tests**

Run: `uv run pytest tests/evaluation -q`

Expected: PASS.

### Task 5: Architecture Documentation and Full Verification

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `README.en.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-07-20-model-independent-loop-apidoc-architecture-design.md`
- Test: `tests/docs/test_model_independent_architecture.py`

**Interfaces:**
- Consumes: the implemented package names and public contracts.
- Produces: English-primary architecture guidance with zh-TW support, while explicitly
  identifying the existing CLI as a compatibility adapter.

- [x] **Step 1: Write documentation synchronization tests**

```python
def test_architecture_docs_name_the_new_product_boundary():
    assert "Evidence Ledger" in Path("docs/ARCHITECTURE.md").read_text()
    assert "Canonical API Contract IR" in Path("README.en.md").read_text()

def test_agent_guidance_stays_synchronized():
    assert Path("AGENTS.md").read_text() == Path("CLAUDE.md").read_text()
```

- [x] **Step 2: Run documentation tests and confirm failures**

Run: `uv run pytest tests/docs/test_model_independent_architecture.py -q`

Expected: FAIL because current teaching docs describe agent-native execution as the product
architecture instead of a replaceable runtime adapter.

- [x] **Step 3: Update architecture and teaching documentation**

Document the new Core/Domain/Ports/Adapters/Evaluation boundaries, state that current CLI
commands remain operational compatibility adapters, link the 2026-07-20 design, keep canonical
English copy and zh-TW support synchronized, align `AGENTS.md` and `CLAUDE.md`, and mark the
spec status implemented.

- [x] **Step 4: Run documentation tests**

Run: `uv run pytest tests/docs/test_model_independent_architecture.py -q`

Expected: PASS.

- [x] **Step 5: Run focused architecture tests**

Run: `uv run pytest tests/domain tests/core tests/adapters tests/evaluation tests/integration/test_evidence_to_release.py tests/docs/test_model_independent_architecture.py -q`

Expected: PASS.

- [x] **Step 6: Run Ruff**

Run: `uv run ruff check .`

Expected: PASS with no lint violations.

- [x] **Step 7: Run the full test suite with coverage**

Run: `uv run pytest --cov=loop_apidoc`

Expected: PASS with coverage at or above 95%.

- [x] **Step 8: Review the spec requirement by requirement**

Confirm model/platform independence, immutable evidence, grounded claim status, deterministic
reconciliation, lifecycle guards, policy/waiver semantics, governance separation, projection
purity, adapter replacement, evaluation isolation, security boundaries, and backward
compatibility all have direct code and test evidence.
