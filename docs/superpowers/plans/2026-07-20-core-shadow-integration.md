# Core Shadow Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `assemble --architecture-mode shadow` path that runs the verified legacy manifest and normalization plan through `EvidenceToContractService`, persists observational Core artifacts, and never changes legacy validation authority or exit codes.

**Architecture:** Add a compatibility-only `loop_apidoc/shadow/` package. Pure bridge functions map legacy manifest and plan values into immutable Core/Domain values; an in-memory runner executes only through Core validation; the report module is the package's sole file-I/O exit and turns every post-run-directory shadow failure into a safe summary.

**Tech Stack:** Python 3.11+, Pydantic v2 immutable models, SHA-256 and canonical JSON from the standard library, existing Core/Domain in-memory adapters, Typer, pytest, Ruff.

**Execution record (2026-07-20):** Completed with red/green TDD cycles for all six
tasks. Final verification: 1,098 tests passed, 81 skipped, total coverage 95.26%;
Ruff, `git diff --check`, architecture-boundary tests, and synchronized-documentation
tests passed.

## Global Constraints

- Shadow execution is opt-in through `--architecture-mode shadow`; `legacy` remains the default.
- The legacy normalization plan, artifacts, validation report, `RunResult`, status, and exit code remain authoritative.
- Shadow runs after legacy validation report persistence, including when legacy validation fails.
- Shadow stops after Core validation and never calls approval, publication, Foundry, a model, the network, a browser, a process, or the system clock.
- Source material is the only factual authority; unresolved evidence remains unverified and missing title/version values are never replaced with fallback text.
- Core and Domain remain unaware of CLI, manifest, normalization-plan, run-directory, and shadow compatibility types.
- `loop_apidoc/shadow/report.py` is the package's only file-I/O exit.
- Successful JSON uses UTF-8, two-space indentation, Pydantic JSON-mode values, and contains no raw source bytes.
- Total test coverage remains at or above 95%.

---

### Task 1: Shadow Values and Comparison

**Files:**
- Create: `loop_apidoc/shadow/__init__.py`
- Create: `loop_apidoc/shadow/models.py`
- Test: `tests/shadow/__init__.py`
- Test: `tests/shadow/test_models.py`

**Interfaces:**
- Consumes: `RunStatus`, `ValidationReport`, `ValidationDecision`, `GroundedClaim`.
- Produces: `ArchitectureMode`, `ShadowStage`, `BridgeDiagnostic`, `ShadowComparison`, `ShadowArtifacts`, and `ShadowExecutionSummary`; `compare_results(report, status, decision, claims, diagnostics) -> ShadowComparison`.

- [ ] **Step 1: Write the failing model and comparison tests**

```python
def test_architecture_mode_defaults_are_string_enums():
    assert ArchitectureMode.LEGACY.value == "legacy"
    assert ArchitectureMode.SHADOW.value == "shadow"

def test_comparison_matches_nonblocking_semantics():
    comparison = compare_results(
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        decision=ValidationDecision(
            verdict=ValidationVerdict.REVIEW,
            policy_profile="shadow",
        ),
        claims=(),
        diagnostics=(),
    )
    assert comparison.verdict_match is True
    assert comparison.legacy_status == "passed"
    assert comparison.core_verdict == "review"
```

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/shadow/test_models.py -q`

Expected: FAIL because `loop_apidoc.shadow` does not exist.

- [ ] **Step 3: Implement immutable shadow values and pure comparison**

Use frozen, extra-forbidden Pydantic models. Count all six `ClaimStatus` values, sort and deduplicate legacy/Core finding codes, and define `verdict_match` as `legacy_report.ok == (decision.verdict is not ValidationVerdict.REJECT)`.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `uv run pytest tests/shadow/test_models.py -q`

Expected: PASS.

### Task 2: Deterministic Source and Evidence Bridge

**Files:**
- Create: `loop_apidoc/shadow/bridge.py`
- Test: `tests/shadow/test_bridge_sources.py`

**Interfaces:**
- Consumes: `Manifest`, `generated_at`.
- Produces: `BridgeInputs(source_set, evidence, citation_fragments, diagnostics, source_set_digest)` from `build_evidence(manifest, generated_at)`.

- [ ] **Step 1: Write failing identity and local-evidence tests**

```python
def test_source_set_identity_ignores_absolute_root_and_manifest_order():
    first = build_evidence(manifest(root="/one", local_sources=[b, a]), NOW)
    second = build_evidence(manifest(root="/two", local_sources=[a, b]), NOW)
    assert first.source_set == second.source_set
    assert first.source_set.id.startswith("source-set-")

def test_usable_local_source_maps_to_one_whole_fragment():
    built = build_evidence(manifest(local_sources=[usable]), NOW)
    assert built.source_set.sources[0].locator == "manual.md"
    assert built.evidence.artifacts[0].content_digest == usable.sha256
    assert built.evidence.fragments[0].locator == "whole"
```

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/shadow/test_bridge_sources.py -q`

Expected: FAIL because `build_evidence` is missing.

- [ ] **Step 3: Implement canonical source-set identities and local evidence**

Canonicalize the metadata list with `json.dumps(source_metadata, sort_keys=True, separators=(",", ":"))`; exclude `sources_root`, runtime identity, and timestamps. Include logical identity, kind, content digest, and usability state. Only `supported=True` plus `ProcessingStatus.PENDING` local sources produce descriptors/artifacts/fragments.

- [ ] **Step 4: Run local tests to verify GREEN**

Run: `uv run pytest tests/shadow/test_bridge_sources.py -q`

Expected: PASS for local cases.

- [ ] **Step 5: Add failing URL, snapshot, and unusable-source tests**

```python
def test_url_without_content_digest_has_no_artifact():
    built = build_evidence(manifest(url_sources=[url(content_sha256=None)]), NOW)
    assert built.source_set.sources[0].kind == "url"
    assert built.evidence.artifacts == ()

def test_url_snapshot_allows_both_exact_citations_to_resolve():
    built = build_evidence(
        manifest(local_sources=[snapshot], url_sources=[url(snapshot_file="snapshot.md")]),
        NOW,
    )
    assert built.citation_fragments[url.url]
    assert built.citation_fragments["snapshot.md"]

@pytest.mark.parametrize("status", [
    ProcessingStatus.IGNORED,
    ProcessingStatus.DUPLICATE,
    ProcessingStatus.UNREADABLE,
    ProcessingStatus.UNSUPPORTED,
])
def test_unusable_local_sources_never_become_evidence(status):
    built = build_evidence(manifest(local_sources=[local(status=status)]), NOW)
    assert built.evidence.artifacts == ()
```

- [ ] **Step 6: Run tests to verify RED**

Run: `uv run pytest tests/shadow/test_bridge_sources.py -q`

Expected: FAIL on URL/snapshot mapping.

- [ ] **Step 7: Implement URL artifacts, snapshot aliases, and exact resolution**

Use URL `content_sha256` only as the content digest; never hash URL text as content. Give URL descriptors no invented media type. Map exact local relative paths and URLs to fragment IDs; a unique snapshot mapping may alias the URL to its local fragment.

- [ ] **Step 8: Run source bridge tests to verify GREEN**

Run: `uv run pytest tests/shadow/test_bridge_sources.py -q`

Expected: PASS.

### Task 3: Claim Proposal and Metadata Bridge

**Files:**
- Modify: `loop_apidoc/shadow/bridge.py`
- Test: `tests/shadow/test_bridge_claims.py`

**Interfaces:**
- Consumes: `NormalizationPlan`, `BridgeInputs`.
- Produces: `build_runtime_result(plan, bridge) -> RuntimeResult`, `build_contract_metadata(plan, bridge) -> ContractMetadata`, and typed `ShadowMetadataError`.

- [ ] **Step 1: Write failing plan-area mapping tests**

```python
def test_supported_endpoint_uses_only_typed_source_values_and_evidence():
    result = build_runtime_result(plan(endpoints=[endpoint]), bridge)
    proposal = result.claim_proposals[0]
    assert proposal.claim_kind == "operation"
    assert proposal.subject == "GET /ping"
    assert proposal.predicate == "definition"
    assert proposal.value == {
        "method": "GET",
        "path": "/ping",
        "summary": "Health",
        "parameters": [],
        "responses": [{"status_code": "200", "description": "OK"}],
    }
    assert proposal.evidence_refs == ("fragment-manual",)
    assert proposal.confidence is None

def test_unverified_value_has_no_evidence_and_missing_value_is_none():
    result = build_runtime_result(plan(endpoints=[unverified, missing]), bridge)
    assert result.claim_proposals[0].evidence_refs == ()
    assert result.claim_proposals[1].value is None
```

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/shadow/test_bridge_claims.py -q`

Expected: FAIL because proposal conversion is missing.

- [ ] **Step 3: Implement typed plan-area proposal conversion**

Map environments, operations, schemas, security, errors, operational constraints, crypto, callbacks, field conditions, and contract tests. Rename only required Domain fields (`responses[].status` to `status_code`, `meaning` to `description`); recursively omit `None`, empty optional collections when the Domain default is empty, status, and citations. Preserve source-stated values without adding conventions.

- [ ] **Step 4: Run mapping tests to verify GREEN**

Run: `uv run pytest tests/shadow/test_bridge_claims.py -q`

Expected: PASS for supported/missing/unverified cases.

- [ ] **Step 5: Add failing citation, conflict, duplicate, determinism, and metadata tests**

```python
def test_unresolved_citation_emits_diagnostic_and_no_reference():
    result = build_runtime_result(plan(endpoints=[endpoint(citation="missing.md")]), bridge)
    assert result.claim_proposals[0].evidence_refs == ()
    assert "missing.md" in result.diagnostics[0]

def test_conflict_without_distinct_values_is_not_fabricated():
    result = build_runtime_result(plan(endpoints=[conflicting_endpoint]), bridge)
    assert result.claim_proposals == ()
    assert any("conflict" in item for item in result.diagnostics)

def test_duplicate_identities_remain_distinct_stable_proposals():
    result = build_runtime_result(plan(endpoints=[first, second]), bridge)
    assert len(result.claim_proposals) == 2
    assert result.claim_proposals[0].id != result.claim_proposals[1].id

def test_metadata_refuses_source_silent_title_or_version():
    with pytest.raises(ShadowMetadataError):
        build_contract_metadata(plan(system_groups=[]), bridge)
```

- [ ] **Step 6: Run tests to verify RED**

Run: `uv run pytest tests/shadow/test_bridge_claims.py -q`

Expected: FAIL on diagnostics/conflicts/metadata.

- [ ] **Step 7: Implement exact citation diagnostics, conflict restraint, stable proposal IDs, and metadata**

Hash plan location, kind, subject, predicate, canonical JSON value, and sorted evidence references. Use fixed runtime identity/version. Build `contract-{source_set_digest[:20]}` and require non-null `resolved_title`/`resolved_version`.

- [ ] **Step 8: Run all bridge tests to verify GREEN**

Run: `uv run pytest tests/shadow/test_bridge_sources.py tests/shadow/test_bridge_claims.py -q`

Expected: PASS.

### Task 4: In-Memory Core Runner and Report Boundary

**Files:**
- Create: `loop_apidoc/shadow/runner.py`
- Create: `loop_apidoc/shadow/report.py`
- Test: `tests/shadow/test_runner.py`
- Test: `tests/shadow/test_report.py`

**Interfaces:**
- Consumes: manifest, plan, legacy validation report/status, run directory, generated time.
- Produces: `execute_shadow(manifest, plan, legacy_report, legacy_status, generated_at) -> ShadowArtifacts`; `run_shadow_safely(manifest, plan, legacy_report, legacy_status, generated_at, run_dir) -> ShadowExecutionSummary`; `write_shadow_artifacts(artifacts, core_dir) -> ShadowExecutionSummary`.

- [ ] **Step 1: Write failing real-service runner test**

```python
def test_runner_executes_through_core_validation_without_approval_or_publication():
    artifacts = execute_shadow(manifest, plan, legacy_report, RunStatus.PASSED, NOW)
    assert artifacts.workflow.state is LifecycleState.APPROVAL_READY
    assert artifacts.artifact_publications == 0
    assert artifacts.approval_requests == 0
    assert artifacts.events[-1].kind == "lifecycle.approval_ready"
```

- [ ] **Step 2: Run runner test to verify RED**

Run: `uv run pytest tests/shadow/test_runner.py -q`

Expected: FAIL because runner is missing.

- [ ] **Step 3: Implement real in-memory Core wiring through validate only**

Wire `StaticSourceAdapter`, `CallableRuntimeAdapter`, all required in-memory stores/sinks, `FixedClock(generated_at)`, `ApiDomainRulePack(version=SHADOW_DOMAIN_VERSION)`, and a rejecting spy approval port. Call register, acquire, request proposals, reconcile, build, and validate; do not call approve or publish.

- [ ] **Step 4: Run runner test to verify GREEN**

Run: `uv run pytest tests/shadow/test_runner.py -q`

Expected: PASS.

- [ ] **Step 5: Write failing report and safe-error tests**

```python
def test_report_writes_complete_stable_artifact_set(tmp_path):
    summary = write_shadow_artifacts(artifacts, tmp_path / "core")
    assert summary.status == "ok"
    assert {path.name for path in (tmp_path / "core").iterdir()} == EXPECTED_FILES
    assert json.loads((tmp_path / "core" / "comparison.json").read_text())["core_verdict"]

def test_safe_entry_point_converts_metadata_failure_to_error_json(tmp_path):
    summary = run_shadow_safely(
        manifest=manifest,
        plan=plan_without_version,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
        run_dir=tmp_path,
    )
    assert summary.status == "error"
    assert json.loads((tmp_path / "core" / "error.json").read_text()) == {
        "status": "error",
        "stage": "bridge",
        "exception_type": "ShadowMetadataError",
        "message": "shadow contract metadata requires a source-stated title and version",
    }
```

- [ ] **Step 6: Run report tests to verify RED**

Run: `uv run pytest tests/shadow/test_report.py -q`

Expected: FAIL because report/safe failure handling is missing.

- [ ] **Step 7: Implement stable JSON reports and non-escaping safe entry point**

Write exactly the nine success files from the design. Stage each bridge, service, comparison, and report action so failures name the active stage. Sanitize exception messages to one line and never serialize traceback or object `repr`. If error-report writing fails, return an in-memory error summary.

- [ ] **Step 8: Run shadow runner/report tests to verify GREEN**

Run: `uv run pytest tests/shadow -q`

Expected: PASS.

### Task 5: Assemble and CLI Integration

**Files:**
- Modify: `loop_apidoc/run/models.py`
- Modify: `loop_apidoc/agentcli/assemble.py`
- Modify: `loop_apidoc/cli.py`
- Test: `tests/agentcli/test_assemble.py`
- Test: `tests/test_cli_assemble.py`

**Interfaces:**
- `run_assemble_pipeline(*, sources_root: Path, extraction_dir: Path, output_root: Path, run_id: str, generated_at: datetime, urls: list[str] | None = None, url_coverage_path: Path | None = None, source_quality_dir: Path | None = None, excludes: Sequence[str] = (), extractor_model: str | None = None, architecture_mode: ArchitectureMode = ArchitectureMode.LEGACY) -> RunResult`.
- `RunResult.shadow: ShadowExecutionSummary | None = None`.
- Typer accepts `--architecture-mode legacy|shadow`.

- [ ] **Step 1: Add failing default and shadow assemble integration tests**

```python
def test_default_assemble_creates_no_core_directory(tmp_path):
    result = _run_demo_pipeline(tmp_path)
    assert result.shadow is None
    assert not (Path(result.run_dir) / "core").exists()

def test_shadow_assemble_writes_core_artifacts_after_legacy_validation(tmp_path):
    result = _run_demo_pipeline(tmp_path, architecture_mode=ArchitectureMode.SHADOW)
    assert result.shadow.status == "ok"
    assert (Path(result.run_dir) / "core" / "comparison.json").is_file()
```

- [ ] **Step 2: Run integration tests to verify RED**

Run: `uv run pytest tests/agentcli/test_assemble.py -k 'default_assemble_creates_no_core or shadow_assemble' -q`

Expected: FAIL because the parameter and summary do not exist.

- [ ] **Step 3: Wire shadow after validation-report persistence**

Call `run_shadow_safely` only after `write_validation_reports`; preserve the existing `status`, descriptor, report, and return semantics. Add only a defaulted optional `RunResult.shadow` field.

- [ ] **Step 4: Run assemble integration tests to verify GREEN**

Run: `uv run pytest tests/agentcli/test_assemble.py -q`

Expected: PASS.

- [ ] **Step 5: Add failing legacy-fail, safe-error, and CLI contract tests**

```python
def test_shadow_runs_when_legacy_validation_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(assemble_mod, "validate_outputs", legacy_failure_report)
    result = _run_demo_pipeline(tmp_path, architecture_mode=ArchitectureMode.SHADOW)
    assert result.status is RunStatus.FAILED
    assert result.shadow is not None

def test_shadow_failure_preserves_original_run_result(tmp_path, monkeypatch):
    monkeypatch.setattr(assemble_mod, "run_shadow_safely", shadow_error_summary)
    result = _run_demo_pipeline(tmp_path, architecture_mode=ArchitectureMode.SHADOW)
    assert result.status is original_status
    assert result.report == original_report
    assert result.shadow.status == "error"

def test_cli_shadow_json_adds_only_shadow_object(tmp_path):
    res = runner.invoke(app, _assemble_args(tmp_path) + [
        "--architecture-mode", "shadow", "--json",
    ])
    payload = json.loads(res.stdout)
    assert payload["shadow"]["status"] in {"ok", "error"}
    assert payload["ok"] == (res.exit_code == 0)

def test_cli_rejects_invalid_architecture_mode(tmp_path):
    res = runner.invoke(app, _assemble_args(tmp_path) + [
        "--architecture-mode", "invalid",
    ])
    assert res.exit_code == 2
```

- [ ] **Step 6: Run CLI tests to verify RED**

Run: `uv run pytest tests/test_cli_assemble.py -k architecture -q`

Expected: FAIL because the CLI option/output additions are missing.

- [ ] **Step 7: Implement CLI option and opt-in output additions**

Default human and JSON payloads remain unchanged. Shadow JSON adds `shadow`; shadow human output appends `；shadow ok` or `；shadow error`. Emit a stderr warning on error without changing the final exit-code expression.

- [ ] **Step 8: Run assemble and CLI tests to verify GREEN**

Run: `uv run pytest tests/agentcli/test_assemble.py tests/test_cli_assemble.py -q`

Expected: PASS.

### Task 6: Documentation and Full Verification

**Files:**
- Modify: `README.en.md`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/introduction.en.html`
- Modify: `docs/introduction.html`
- Modify: `docs/onboarding.en.html`
- Modify: `docs/onboarding.html`
- Modify: `docs/operator-manual.en.html`
- Modify: `docs/operator-manual.html`
- Modify: `docs/architecture-manual.en.html`
- Modify: `docs/architecture-manual.html`
- Modify: `skills/loop-apidoc/reference/assemble-and-correction.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Test: `tests/docs/test_core_shadow_documentation.py`

**Interfaces:**
- Teaching copy documents the flag, artifact directory, observational authority, and report I/O boundary in English-primary and zh-TW-supporting pairs.

- [ ] **Step 1: Write a failing synchronized-documentation test**

```python
@pytest.mark.parametrize("path", REQUIRED_DOCS)
def test_shadow_mode_is_documented_everywhere(path):
    text = Path(path).read_text(encoding="utf-8")
    assert "--architecture-mode shadow" in text
    assert "core/" in text

def test_agent_guides_name_shadow_report_as_file_io_exit():
    for path in ("AGENTS.md", "CLAUDE.md"):
        assert "shadow/report.py" in Path(path).read_text(encoding="utf-8")
```

- [ ] **Step 2: Run docs test to verify RED**

Run: `uv run pytest tests/docs/test_core_shadow_documentation.py -q`

Expected: FAIL because teaching documents do not yet describe shadow mode.

- [ ] **Step 3: Update all English/zh-TW teaching and agent-guidance documents**

Add concise, paired text stating that shadow output is observational; legacy validation, score, approval, Foundry, and exit codes remain unchanged. Add `core/` to run trees and `shadow/report.py` to file-I/O exits.

- [ ] **Step 4: Run docs and focused feature tests**

Run: `uv run pytest tests/docs/test_core_shadow_documentation.py tests/shadow tests/agentcli/test_assemble.py tests/test_cli_assemble.py -q`

Expected: PASS.

- [ ] **Step 5: Run complete coverage and lint verification**

Run: `uv run pytest --cov=loop_apidoc`

Expected: PASS with total coverage at least 95%.

Run: `uv run ruff check .`

Expected: PASS with no lint findings.

- [ ] **Step 6: Review the final diff and package boundaries**

Run: `git diff --check && uv run pytest tests/core/test_architecture_boundaries.py -q`

Expected: both commands PASS; `loop_apidoc/core/` and `loop_apidoc/domain/` contain no compatibility or platform imports.
