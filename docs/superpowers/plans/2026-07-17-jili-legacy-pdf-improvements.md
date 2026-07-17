# JiLi Legacy PDF Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faithfully generate and score legacy PDF APIs with shared GET/POST contracts while exposing missing server URLs and preserving JiLi as a regression benchmark.

**Architecture:** Normalize the additive `methods` field at the agent-native extraction boundary, so all existing plan and generator code continues to consume canonical single-method operations. Completeness reports a source-grounded server gap; score evaluation uses plan missing metadata to distinguish declared source absence from unclassified extraction gaps. The benchmark stores only reproducible extraction and expectations.

**Tech Stack:** Python 3.11, Pydantic, pytest, loop-apidoc CLI.

## Global Constraints

- Preserve every existing `method`-only extraction file and output unchanged.
- Never infer method-specific request differences; `methods` only expands an identical declared contract.
- Base URL absence is a non-blocking warning; never fabricate a server.
- A source-declared missing example remains visible in validation and score findings but has zero score impact.
- Do not commit the JiLi PDF or derived source text.

---

### Task 1: Add multi-method extraction normalization and cross-file identity support

**Files:**
- Modify: `loop_apidoc/agentcli/extraction.py`
- Modify: `loop_apidoc/agentcli/cross_file.py`
- Modify: `loop_apidoc/agentcli/input_schema.py`
- Modify: `skills/loop-apidoc/reference/extraction-schemas.md`
- Test: `tests/agentcli/test_collapsed_extraction.py`
- Test: `tests/agentcli/test_cross_file.py`

**Interfaces:**
- Consumes: endpoint dictionaries with legacy `method: str` or additive `methods: list[str]`.
- Produces: canonical stage-05 and stage-06 JSON answers containing one `method` per operation.

- [ ] **Step 1: Write failing cross-file tests for one `methods` detail matching two inventory methods**

```python
def test_multi_method_detail_satisfies_expanded_inventory_identities():
    inventory = {"endpoints": [{"methods": ["GET", "POST"], "path": "/free-spin"}]}
    endpoints = [("ep00.json", {"methods": ["GET", "POST"], "path": "/free-spin"})]
    assert cross_file_violations(inventory, endpoints) == []
```

```python
def test_multi_method_detail_rejects_missing_inventory_method():
    inventory = {"endpoints": [{"methods": ["GET", "POST"], "path": "/free-spin"}]}
    endpoints = [("ep00.json", {"methods": ["GET"], "path": "/free-spin"})]
    assert any("POST /free-spin" in item for item in cross_file_violations(inventory, endpoints))
```

- [ ] **Step 2: Run the focused cross-file tests and verify the new tests fail**

Run: `uv run pytest tests/agentcli/test_cross_file.py -q`

Expected: failure because `methods` is not expanded by the current identity logic.

- [ ] **Step 3: Write a failing extraction normalization test**

```python
def test_inventory_to_stage_answers_expands_methods_to_single_method_entries():
    answers = inventory_to_stage_answers({"endpoints": [
        {"methods": ["GET", "POST"], "path": "/free-spin", "summary": "Free spin"}
    ]})
    payload = extract_json_block(answers["05"])
    assert [entry["method"] for entry in payload["endpoints"]] == ["GET", "POST"]
    assert all("methods" not in entry for entry in payload["endpoints"])
```

- [ ] **Step 4: Run the focused extraction test and verify it fails**

Run: `uv run pytest tests/agentcli/test_collapsed_extraction.py -q`

Expected: failure because stage answers currently retain the unexpanded entry.

- [ ] **Step 5: Implement the minimal normalizer**

```python
def _methods(entry: dict) -> list[str]:
    raw = entry.get("methods")
    if isinstance(raw, list):
        return [value.upper() for value in raw if isinstance(value, str) and value.strip()]
    method = entry.get("method")
    return [method] if isinstance(method, str) and method.strip() else []

def _expand_methods(entries: list[dict]) -> list[dict]:
    expanded = []
    for entry in entries:
        for method in _methods(entry):
            expanded.append({key: value for key, value in entry.items() if key != "methods"} | {"method": method})
    return expanded
```

Use `_expand_methods` for inventory stage 05 and endpoint detail ingestion; update cross-file expected identities, file-count logic, and duplicate detection to work on expanded entries. Add `methods` to the tolerated extraction schema and document its identical-contract constraint.

- [ ] **Step 6: Run focused tests and existing extraction boundary tests**

Run: `uv run pytest tests/agentcli/test_cross_file.py tests/agentcli/test_collapsed_extraction.py tests/agentcli/test_input_schema.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add loop_apidoc/agentcli/extraction.py loop_apidoc/agentcli/cross_file.py loop_apidoc/agentcli/input_schema.py skills/loop-apidoc/reference/extraction-schemas.md tests/agentcli/test_cross_file.py tests/agentcli/test_collapsed_extraction.py
git commit -m "feat: normalize shared endpoint methods"
```

### Task 2: Surface missing concrete server URLs as a completeness warning

**Files:**
- Modify: `loop_apidoc/validate/completeness.py`
- Test: `tests/validate/test_completeness.py`

**Interfaces:**
- Consumes: `NormalizationPlan.endpoints` and `NormalizationPlan.environments`.
- Produces: one warning at `servers` only for path-bearing APIs with no non-empty `base_url`.

- [ ] **Step 1: Write failing validation tests**

```python
def test_path_operations_without_base_url_report_server_warning():
    plan = _plan(environments=[])
    issue = next(i for i in check_completeness(plan) if i.location == "servers")
    assert issue.severity is Severity.WARNING
    assert issue.code is IssueCode.REQUIRED_INFO_MISSING

def test_webhooks_without_base_url_do_not_report_server_warning():
    plan = _plan(environments=[], endpoints=[_endpoint(path=None, method="POST")])
    assert not any(i.location == "servers" for i in check_completeness(plan))
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `uv run pytest tests/validate/test_completeness.py -q`

Expected: failure because `check_completeness` has no server-coverage rule.

- [ ] **Step 3: Implement the minimal predicate and warning**

```python
def _has_path_operation(plan: NormalizationPlan) -> bool:
    return any(endpoint.path for endpoint in plan.endpoints)

def _has_base_url(plan: NormalizationPlan) -> bool:
    return any((environment.base_url or "").strip() for environment in plan.environments)
```

Append a `REQUIRED_INFO_MISSING` warning with `location="servers"`, a source-grounding message, and no endpoint requery target when `_has_path_operation(plan) and not _has_base_url(plan)`.

- [ ] **Step 4: Run focused validation tests**

Run: `uv run pytest tests/validate/test_completeness.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/validate/completeness.py tests/validate/test_completeness.py
git commit -m "feat: warn when API server URL is absent"
```

### Task 3: Score declared source gaps without completeness penalty

**Files:**
- Modify: `loop_apidoc/score/evaluate.py`
- Modify: `loop_apidoc/score/models.py`
- Test: `tests/score/test_evaluate.py`

**Interfaces:**
- Consumes: `ScoreInputs.plan["missing_items"]` and validation warnings.
- Produces: `ScoreFinding` entries with zero `score_impact` for matching source-declared example gaps.

- [ ] **Step 1: Write failing score tests**

```python
def test_declared_missing_examples_remain_visible_without_penalty():
    issue = _issue(IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING, "paths./ping.get")
    inputs = _inputs([issue], plan={"missing_items": [{"area": "06", "detail": "examples", "query_id": "paths./ping.get"}]})
    report = evaluate_score(inputs, profile=ScoreProfile.CI)
    assert report.findings[0].score_impact == 0
    assert report.category_scores["completeness"] == 100

def test_unclassified_missing_examples_keep_penalty():
    issue = _issue(IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING, "paths./ping.get")
    report = evaluate_score(_inputs([issue]), profile=ScoreProfile.CI)
    assert report.findings[0].score_impact == 12
```

Extend `_inputs` to accept `plan` and place it in `ScoreInputs`.

- [ ] **Step 2: Run score tests and verify the declared-gap test fails**

Run: `uv run pytest tests/score/test_evaluate.py -q`

Expected: declared missing example still has score impact 12.

- [ ] **Step 3: Implement explicit source-declared example-gap classification**

```python
def _declared_example_gap(issue: Issue, plan: dict | None) -> bool:
    if issue.code is not IssueCode.REQUIRED_INFO_MISSING or issue.field_path != "examples":
        return False
    return any(
        item.get("query_id") == issue.location and "example" in str(item.get("detail", "")).lower()
        for item in (plan or {}).get("missing_items", []) if isinstance(item, dict)
    )
```

Pass `score_impact=0` to `_finding_from_issue` for that case; retain the original severity, category, evidence, and suggested fix.

- [ ] **Step 4: Run score tests**

Run: `uv run pytest tests/score/test_evaluate.py tests/score/test_loop.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/score/evaluate.py loop_apidoc/score/models.py tests/score/test_evaluate.py
git commit -m "feat: score declared example gaps faithfully"
```

### Task 4: Add the JiLi legacy PDF benchmark fixture and regression assertions

**Files:**
- Create: `benchmarks/jili-legacy-gaming-pdf/extraction/inventory.json`
- Create: `benchmarks/jili-legacy-gaming-pdf/extraction/integration.json`
- Create: `benchmarks/jili-legacy-gaming-pdf/extraction/endpoints/ep00.json` through `ep19.json`
- Create: `benchmarks/jili-legacy-gaming-pdf/expected/minimum.json`
- Create: `benchmarks/jili-legacy-gaming-pdf/expected/validation.expect.json`
- Create: `benchmarks/jili-legacy-gaming-pdf/notes.md`
- Modify: `benchmarks/README.md`
- Test: `tests/test_benchmarks.py`

**Interfaces:**
- Consumes: the manually verified JiLi extraction produced in `/Users/carl/Dev/CMG/GamingHub/providers/jili/docs/loop-apidoc-benchmark-work`.
- Produces: a source-gitignored, repeatable benchmark whose extraction passes `verify_extraction_dir` and whose expected warning map includes source gaps.

- [ ] **Step 1: Write the failing benchmark expectation test**

```python
def test_jili_case_has_declared_legacy_pdf_minimums():
    case = _case_by_name("jili-legacy-gaming-pdf")
    minimum = json.loads((case / "expected" / "minimum.json").read_text("utf-8"))
    assert minimum["must_have"]["endpoints_min"] == 25
    assert "paths./CreateFreeSpin.get" in minimum["critical_operations"]
    assert "paths./CreateFreeSpin.post" in minimum["critical_operations"]
```

- [ ] **Step 2: Run the focused benchmark test and verify it fails**

Run: `uv run pytest tests/test_benchmarks.py::test_jili_case_has_declared_legacy_pdf_minimums -q`

Expected: failure because the case does not exist.

- [ ] **Step 3: Create the fixture from the verified run**

Copy only extraction JSON, minimum expectations, warning expectations, and notes. Replace the duplicated GET/POST FreeSpin entries with the new `methods` representation. Record SHA-256 `729c4bb8ff74caf5127376d090231101d81efd6b3321f9ddf47e51f6b94508e6`, source version `1.0.52`, expected absent base URL, and expected source-declared example gaps. Do not copy PDF, preprocessed Markdown, output, or generated examples.

- [ ] **Step 4: Run extraction and benchmark tests**

Run: `uv run pytest tests/agentcli/test_input_schema.py tests/test_benchmarks.py -q`

Expected: fixture contract tests pass; end-to-end benchmark skips only if the operator-provided PDF is absent.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/jili-legacy-gaming-pdf benchmarks/README.md tests/test_benchmarks.py
git commit -m "test: add JiLi legacy PDF benchmark"
```

### Task 5: Run repository validation and inspect the JiLi result

**Files:**
- No production changes.

- [ ] **Step 1: Run targeted suites**

Run: `uv run pytest tests/agentcli tests/validate/test_completeness.py tests/score/test_evaluate.py tests/test_benchmarks.py -q`

Expected: PASS, with only source-absence benchmark skips if the local JiLi source was not linked under the benchmark case.

- [ ] **Step 2: Run project quality gate**

Run: `uv run python scripts/quality_gate.py --strict-local`

Expected: exit 0, or report only documented absent copyrighted benchmark sources.

- [ ] **Step 3: Assemble JiLi with score**

Run: `uv run loop-apidoc assemble --sources benchmarks/jili-legacy-gaming-pdf/sources --extraction benchmarks/jili-legacy-gaming-pdf/extraction --output /tmp/jili-benchmark --score --target-score 85 --round-index 1 --max-rounds 6 --json`

Expected: validation has no errors; the report contains a `servers` warning; declared example gaps remain visible but do not receive score penalties.

- [ ] **Step 4: Review final diff and status**

Run: `git diff --check && git status --short && git log --oneline -4`

Expected: no whitespace errors and only intended commits/files.
