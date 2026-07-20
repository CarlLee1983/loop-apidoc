# Release Blocker Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the three 0.16.0 release blockers in generated crypto examples, `review.html`, and strict-local benchmark discovery without weakening source grounding.

**Architecture:** Keep generation deterministic and fix each defect at the projection boundary that owns it. Crypto rendering gets one shared supported-algorithm predicate used by imports, runnable blocks, and request wiring; review rows are projected from generated OpenAPI and enriched from plan/provenance; the quality gate keeps an explicit required tuple whose test is derived independently from committed benchmark fixtures.

**Tech Stack:** Python 3.11+, Pydantic v2 models, pytest, Ruff, `uv`

## Global Constraints

- Source documents remain the only source of truth; unsupported crypto must render a gap and never an approximation.
- Runnable request crypto requires an explicit `algorithm` and `payload_assembly`, confirmed CBC mode, and the AES algorithm family.
- DES, MD5, GCM, and other unsupported algorithms must not be wired into generated request bodies or headers.
- The review Schema metric and table must describe `result.openapi.components.schemas`.
- `REQUIRED_BENCHMARK_CASES` must exactly match committed cases containing both `extraction/inventory.json` and `expected/validation.expect.json`.
- No command or CLI flag changes.
- Do not commit, push, tag, or publish unless the user separately requests it.

---

### Task 1: Fail Closed for Unsupported Crypto Algorithms

**Files:**
- Modify: `tests/test_generate_examples.py`
- Modify: `loop_apidoc/generate/examples.py`
- Modify: `tests/test_validate_integration.py`
- Modify: `loop_apidoc/validate/integration.py`

**Interfaces:**
- Consumes: `CryptoScheme.algorithm`, `.mode`, `.payload_assembly`, and `.verify`
- Produces: `_is_aes(scheme: CryptoScheme) -> bool` and `_is_runnable_crypto(scheme: CryptoScheme) -> bool`

- [x] **Step 1: Write failing DES-CBC regression tests**

```python
def _des_cbc_scheme() -> CryptoScheme:
    return CryptoScheme(
        status="supported",
        name="Data",
        purpose="request",
        algorithm="DES-CBC",
        mode="CBC",
        payload_assembly=[{"step": 1, "desc": "encrypt", "fields": ["account"]}],
        verify=CryptoVerify(field="Data"),
    )


def test_render_py_des_cbc_is_gap_without_aes_or_request_wiring():
    out = _render_py(_shape(body=[("Data", "placeholder", "<data>")]), [_des_cbc_scheme()])
    assert "DES-CBC" in out and "# gap:" in out and "NotImplementedError" in out
    assert "from Crypto.Cipher import AES" not in out
    assert "AES.new(" not in out
    assert 'payload["Data"] = sign(' not in out


def test_render_ts_des_cbc_is_gap_without_cipher_or_request_wiring():
    out = _render_ts(_shape(body=[("Data", "placeholder", "<data>")]), [_des_cbc_scheme()])
    assert "DES-CBC" in out and "// gap:" in out and "throw new Error" in out
    assert "createCipheriv" not in out
    assert '(body as any)["Data"] = sign(' not in out


def test_des_cbc_shell_and_readme_do_not_claim_request_scripts_generate_value():
    shell = _render_curl(_shape(body=[("Data", "placeholder", "<data>")]), [_des_cbc_scheme()])
    readme = _render_readme(["Transfer"], [_des_cbc_scheme()])
    assert "請先跑 request.py / request.ts 取得簽章值" not in shell
    assert "簽章值請先跑 request.py / request.ts 取得" not in readme
    assert "不支援" in shell and "不支援" in readme
```

- [x] **Step 2: Run the tests and confirm they fail because DES-CBC is treated as runnable AES**

Run: `uv run pytest tests/test_generate_examples.py -k "des_cbc" -q`

Expected: FAIL on emitted AES/createCipheriv code and request wiring.

- [x] **Step 3: Add one shared runnable predicate and algorithm-specific gap rendering**

```python
def _is_aes(scheme: CryptoScheme) -> bool:
    algorithm = (scheme.algorithm or "").upper()
    return bool(re.search(r"(^|[^A-Z0-9])AES([^A-Z0-9]|$)", algorithm))


def _is_runnable_crypto(scheme: CryptoScheme) -> bool:
    return _signature_explicit(scheme) and _is_cbc(scheme) and _is_aes(scheme)
```

Use `_is_runnable_crypto` in `_wire_target`, runnable import selection, runnable block selection, and validator wiring checks. For an explicit CBC scheme that is not AES, emit a gap naming `scheme.algorithm` and raise at runtime. Make curl and README guidance capability-aware: only runnable AES-CBC schemes may direct the reader to generated values; unsupported schemes must explicitly say the scripts expose a gap and do not produce that value.

- [x] **Step 4: Add and run a validator regression for unsupported DES-CBC wiring**

```python
def test_unsupported_des_cbc_does_not_require_request_wiring():
    des = _runnable_crypto(field="Msg").model_copy(
        update={"algorithm": "DES", "name": "DES Encryption"}
    )
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[des]),
    )
    examples = {
        "examples/Deposit/request.py": 'payload = {\n    "Msg": "<msg>",\n}\n'
    }
    codes = [
        issue.code
        for issue in check_integration(plan, _result_with_examples(examples))
    ]
    assert IssueCode.OUTPUT_MISMATCH not in codes
```

- [x] **Step 5: Run focused and full example tests**

Run: `uv run pytest tests/test_generate_examples.py -q`

Expected: PASS, including existing AES-CBC and GCM regressions.

### Task 2: Project Review Schemas from Generated OpenAPI

**Files:**
- Modify: `tests/generate/test_review_html.py`
- Modify: `loop_apidoc/generate/review.py`

**Interfaces:**
- Consumes: `result.openapi["components"]["schemas"]`, `result.provenance.entries`, and `plan.schemas`
- Produces: `_schema_rows(plan: NormalizationPlan, result: GenerateResult) -> str`

- [x] **Step 1: Write a failing ErrorCode review regression**

```python
def test_review_html_includes_openapi_derived_error_code_schema(tmp_path):
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        errors=[
            ErrorEntry(
                status=PlanItemStatus.SUPPORTED,
                code="1001",
                meaning="Invalid token",
                citations=[_cite()],
            )
        ],
    )
    generate_outputs(plan, _manifest(), tmp_path)
    html = (tmp_path / "review.html").read_text(encoding="utf-8")
    assert "<span>Schema</span><strong>1</strong>" in html
    assert "<code>ErrorCode</code>" in html
    assert "有來源" in html
    assert "manual.md" in html
```

- [x] **Step 2: Run the regression and confirm the metric/table omit ErrorCode**

Run: `uv run pytest tests/generate/test_review_html.py::test_review_html_includes_openapi_derived_error_code_schema -q`

Expected: FAIL because the Schema metric is zero and the table is empty.

- [x] **Step 3: Build OpenAPI-backed schema rows with plan/provenance enrichment**

Create a plan component-key lookup using `schema_key_map(plan.schemas)`. Iterate the generated schema map; for mapped plan schemas retain `name`, `status`, and `citations`. Otherwise use `schema.get("title") or component_key`, aggregate exact-target provenance status with fail-closed priority, and pass matching provenance entries to `_source_refs`. Count `properties` and `required` from the generated schema dictionaries.

- [x] **Step 4: Run focused review tests**

Run: `uv run pytest tests/generate/test_review_html.py -q`

Expected: PASS, including the existing empty and explicit-plan schema paths.

### Task 3: Lock Strict-Local Required Cases to Committed Fixtures

**Files:**
- Modify: `tests/test_quality_gate.py`
- Modify: `scripts/quality_gate.py`

**Interfaces:**
- Consumes: committed `benchmarks/*/extraction/inventory.json` and `benchmarks/*/expected/validation.expect.json`
- Produces: exact `REQUIRED_BENCHMARK_CASES` parity for all 13 cases

- [x] **Step 1: Replace the subset assertion with an independent fixture-discovery assertion**

```python
def test_required_benchmark_cases_match_committed_cases():
    benchmark_root = Path(__file__).resolve().parents[1] / "benchmarks"
    committed = {
        case.name
        for case in benchmark_root.iterdir()
        if (case / "extraction" / "inventory.json").is_file()
        and (case / "expected" / "validation.expect.json").is_file()
    }
    assert set(quality_gate.required_benchmark_cases()) == committed
    assert len(quality_gate.required_benchmark_cases()) == len(committed)
```

- [x] **Step 2: Run the parity test and confirm the three missing cases**

Run: `uv run pytest tests/test_quality_gate.py -k "required_benchmark_cases" -q`

Expected: FAIL showing `jili-legacy-gaming-pdf`, `funkygames-transfer-operator`, and `rsg-game-transfer-wallet` are absent.

- [x] **Step 3: Add the three committed cases to `REQUIRED_BENCHMARK_CASES`**

Append the three case names in `scripts/quality_gate.py` without changing preflight behavior.

- [x] **Step 4: Run quality-gate unit tests**

Run: `uv run pytest tests/test_quality_gate.py -q`

Expected: PASS.

### Task 4: Release Documentation and Verification

**Files:**
- Modify: `docs/RELEASE_NOTES_0.16.0.md`
- Review without unnecessary edits: `README.en.md`, `README.md`, `docs/index.html`, `docs/introduction.html`, `docs/onboarding.html`, `docs/operator-manual.html`, `docs/architecture-manual.html`, `AGENTS.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: fresh verification output
- Produces: release notes with blocker fixes and current validation counts

- [x] **Step 1: Update release notes with all three fixes**

Add English-primary and Traditional-Chinese summary bullets covering algorithm-specific fail-closed crypto gaps, generated-OpenAPI schema review projection, and 13-case strict-local parity.

- [x] **Step 2: Run focused regression verification**

Run: `uv run pytest tests/test_generate_examples.py tests/generate/test_review_html.py tests/test_quality_gate.py -q`

Expected: PASS.

- [x] **Step 3: Run repository verification**

Run:

```bash
uv run ruff check .
uv run pytest --cov=loop_apidoc
uv run python scripts/quality_gate.py
uv run pytest tests/test_benchmarks.py -ra
```

Expected: Ruff, coverage suite, and CI-safe quality gate pass. Benchmark output may skip cases whose operator-provided source snapshots are absent, but must discover all 13.

- [x] **Step 4: Run strict-local preflight, artifact, package, and tag dry-run checks**

Run the strict-local preflight and confirm its expected failure lists every source-less required case. Assemble a fresh RSG shadow run from its committed extraction and available source snapshot, inspect DES-CBC generated examples and review ErrorCode assertions, build/install the package in an isolated temporary environment, and run:

`npm run release:tag -- --message "loop-apidoc 0.16.0" --dry-run`

- [x] **Step 5: Record fresh counts and review the final diff**

Update `docs/RELEASE_NOTES_0.16.0.md` only with counts observed in this implementation run. Run `git diff --check`, inspect `git diff --stat`, and confirm no unrelated user changes were modified.
