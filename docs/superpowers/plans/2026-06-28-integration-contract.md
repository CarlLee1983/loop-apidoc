# integration-contract.json Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-grounded, citation-backed, machine-readable `integration-contract.json` product capturing the API's integration-mechanics layer (crypto/signature chains, callbacks, cross-field conditions, test cases) on top of the existing OpenAPI/Markdown outputs.

**Architecture:** A new read-only subagent extraction stage writes `integration.json`; `assemble` reads it, `plan/integration.py` converts it into a cited `IntegrationContract` (reusing already-structured `plan.errors`/`environments`), `generate/integration.py` emits `integration-contract.json` plus `integration.*` provenance targets, `markdown.py` adds a human-readable section, and `validate/integration.py` enforces no-speculation + reference resolution + signal-word gap detection. The `manifest→plan→generate→validate` backbone is unchanged; each stage merely learns about the contract.

**Tech Stack:** Python ≥3.11, uv, pydantic v2, typer, pytest, ruff.

## Global Constraints

- **Core invariant:** sources are the only truth. Any contract field the sources do not state stays `null` and is recorded in the contract's `missing` — never inferred, never filled with REST/payment conventions.
- **Single file-I/O exit:** only `generate/` (`generate_outputs`) and `run/` write files. `plan/integration.py`, `generate/integration.py` (the *builder*), and `validate/integration.py` must be pure functions; only `generate_outputs` does the actual write.
- **Immutable patterns:** return new values; do not mutate inputs (use `model_copy(update=...)`).
- **Provenance ↔ validation alignment:** every contract leaf entering the output traces to a source-grounded citation, or the no-speculation check flags it.
- **Python ≥3.11**, managed with `uv` (no `pip`). Run tests with `uv run pytest`; lint with `uv run ruff check .`.
- **SKILL.md is written in English**; generated *product* output (markdown, contract field rendering in the guide) remains `zh-TW`.
- New provenance target namespace, verbatim:
  - `integration.crypto.{name}`
  - `integration.callbacks.{name}`
  - `integration.field_conditions.{index}`
  - `integration.test_cases.{name}`
  - `error_codes` reuses `plan.errors` citations and gets **no** `integration.*` target.

---

### Task 1: Contract plan models

**Files:**
- Modify: `loop_apidoc/plan/models.py` (append new models + add `integration` field to `NormalizationPlan`)
- Test: `tests/test_plan_integration_models.py`

**Interfaces:**
- Consumes: existing `_Cited`, `SourceCitation`, `PlanItemStatus`, `NormalizationPlan` from `loop_apidoc/plan/models.py`.
- Produces:
  - `CryptoStep(BaseModel)` — `step: int | None`, `desc: str | None`, `fields: list[str] = []`
  - `KeySource(BaseModel)` — `key: str | None = None`, `iv: str | None = None`, `note: str | None = None`
  - `CryptoVerify(BaseModel)` — `field: str | None = None`, `method: str | None = None`, `desc: str | None = None`
  - `CryptoScheme(_Cited)` — `name`, `purpose`, `algorithm`, `mode`, `padding`, `encoding` (all `str | None = None`), `key_source: KeySource | None = None`, `payload_assembly: list[CryptoStep] = []`, `verify: CryptoVerify | None = None`
  - `Callback(_Cited)` — `name`, `trigger`, `transport`, `payload_ref`, `verification`, `expected_response` (all `str | None = None`)
  - `FieldCondition(_Cited)` — `scope: str | None = None`, `rule: str | None = None`, `when: str | None = None`, `then_required: list[str] = []`
  - `ContractTestCase(_Cited)` — `name: str | None = None`, `operation_ref: str | None = None`, `request: dict | None = None`, `response: dict | None = None`
  - `ContractMissing(BaseModel)` — `area: str`, `detail: str`
  - `IntegrationContract(BaseModel)` — `version: str = "1.0"`, `crypto: list[CryptoScheme] = []`, `callbacks: list[Callback] = []`, `field_conditions: list[FieldCondition] = []`, `test_cases: list[ContractTestCase] = []`, `missing: list[ContractMissing] = []`
  - `NormalizationPlan.integration: IntegrationContract | None = None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plan_integration_models.py
from loop_apidoc.plan.models import (
    CryptoScheme,
    CryptoStep,
    IntegrationContract,
    NormalizationPlan,
    PlanItemStatus,
)


def test_crypto_scheme_defaults_and_cited():
    scheme = CryptoScheme(status=PlanItemStatus.SUPPORTED, name="TradeInfo 加密")
    assert scheme.algorithm is None
    assert scheme.payload_assembly == []
    assert scheme.citations == []
    assert scheme.status is PlanItemStatus.SUPPORTED


def test_crypto_step_order_preserved():
    steps = [CryptoStep(step=2, desc="b"), CryptoStep(step=1, desc="a")]
    contract = IntegrationContract(
        crypto=[CryptoScheme(status=PlanItemStatus.SUPPORTED, payload_assembly=steps)]
    )
    assert [s.step for s in contract.crypto[0].payload_assembly] == [2, 1]


def test_plan_integration_defaults_none():
    plan = NormalizationPlan(notebook_url="x")
    assert plan.integration is None
    plan2 = plan.model_copy(update={"integration": IntegrationContract()})
    assert plan2.integration.version == "1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plan_integration_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'CryptoScheme'`

- [ ] **Step 3: Write minimal implementation**

Append to `loop_apidoc/plan/models.py` (after `OperationalEntry`, before `NormalizationPlan`):

```python
class CryptoStep(BaseModel):
    step: int | None = None
    desc: str | None = None
    fields: list[str] = Field(default_factory=list)


class KeySource(BaseModel):
    key: str | None = None
    iv: str | None = None
    note: str | None = None


class CryptoVerify(BaseModel):
    field: str | None = None
    method: str | None = None
    desc: str | None = None


class CryptoScheme(_Cited):
    name: str | None = None
    purpose: str | None = None  # request | response | callback | signature
    algorithm: str | None = None
    mode: str | None = None
    padding: str | None = None
    encoding: str | None = None
    key_source: KeySource | None = None
    payload_assembly: list[CryptoStep] = Field(default_factory=list)
    verify: CryptoVerify | None = None


class Callback(_Cited):
    name: str | None = None
    trigger: str | None = None
    transport: str | None = None
    payload_ref: str | None = None
    verification: str | None = None
    expected_response: str | None = None


class FieldCondition(_Cited):
    scope: str | None = None
    rule: str | None = None
    when: str | None = None
    then_required: list[str] = Field(default_factory=list)


class ContractTestCase(_Cited):
    name: str | None = None
    operation_ref: str | None = None
    request: dict | None = None
    response: dict | None = None


class ContractMissing(BaseModel):
    area: str
    detail: str


class IntegrationContract(BaseModel):
    version: str = "1.0"
    crypto: list[CryptoScheme] = Field(default_factory=list)
    callbacks: list[Callback] = Field(default_factory=list)
    field_conditions: list[FieldCondition] = Field(default_factory=list)
    test_cases: list[ContractTestCase] = Field(default_factory=list)
    missing: list[ContractMissing] = Field(default_factory=list)
```

Then add the field to `NormalizationPlan` (alongside the other list fields):

```python
    integration: IntegrationContract | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_plan_integration_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/plan/models.py tests/test_plan_integration_models.py
git commit -m "feat: [plan] integration-contract data models"
```

---

### Task 2: Build contract from agent JSON (`plan/integration.py`)

**Files:**
- Create: `loop_apidoc/plan/integration.py`
- Test: `tests/test_plan_integration_builder.py`

**Interfaces:**
- Consumes: `classify_item(locator, *, query_id, answer_path, manifest) -> tuple[PlanItemStatus, SourceCitation]` from `loop_apidoc/plan/classify.py`; `NormalizationPlan`, `IntegrationContract`, `CryptoScheme`, `CryptoStep`, `KeySource`, `CryptoVerify`, `Callback`, `FieldCondition`, `ContractTestCase`, `ContractMissing` from `loop_apidoc/plan/models.py`; `Manifest` from `loop_apidoc/manifest/models.py`.
- Produces: `build_integration_contract(integration_json: dict | None, plan: NormalizationPlan, manifest: Manifest) -> IntegrationContract`. Each leaf entry's `status`/`citations` come from `classify_item` on the entry's `"source"` string, with `query_id="integration"` and `answer_path="integration.json"`. When `integration_json` is `None` or empty, returns an `IntegrationContract()` with all sections empty (sources stated nothing → not a failure).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plan_integration_builder.py
from datetime import datetime, timezone

from loop_apidoc.manifest.models import Manifest, ManifestSource, SourceStatus
from loop_apidoc.plan.integration import build_integration_contract
from loop_apidoc.plan.models import NormalizationPlan, PlanItemStatus


def _manifest() -> Manifest:
    return Manifest(
        generated_at=datetime(2026, 6, 28, tzinfo=timezone.utc),
        sources=[
            ManifestSource(
                locator="newebpay.pdf",
                kind="pdf",
                status=SourceStatus.READABLE,
            )
        ],
    )


def test_none_input_yields_empty_contract():
    contract = build_integration_contract(None, NormalizationPlan(notebook_url="x"), _manifest())
    assert contract.crypto == []
    assert contract.callbacks == []
    assert contract.missing == []


def test_crypto_scheme_built_and_cited():
    payload = {
        "crypto": [
            {
                "name": "TradeInfo 加密",
                "purpose": "request",
                "algorithm": "AES",
                "mode": "CBC",
                "key_source": {"key": "HashKey", "iv": "HashIV"},
                "payload_assembly": [{"step": 1, "desc": "query string 化", "fields": ["MerchantID"]}],
                "verify": {"field": "TradeSha", "method": "SHA256"},
                "source": "newebpay.pdf p.12",
            }
        ]
    }
    contract = build_integration_contract(payload, NormalizationPlan(notebook_url="x"), _manifest())
    assert len(contract.crypto) == 1
    scheme = contract.crypto[0]
    assert scheme.algorithm == "AES"
    assert scheme.key_source.key == "HashKey"
    assert scheme.payload_assembly[0].step == 1
    assert scheme.status is PlanItemStatus.SUPPORTED
    assert scheme.citations[0].locator == "newebpay.pdf p.12"


def test_explicit_missing_recorded_not_failed():
    payload = {"missing": [{"area": "crypto.padding", "detail": "來源未述 padding"}]}
    contract = build_integration_contract(payload, NormalizationPlan(notebook_url="x"), _manifest())
    assert contract.missing[0].area == "crypto.padding"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plan_integration_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.plan.integration'`

- [ ] **Step 3: Write minimal implementation**

```python
# loop_apidoc/plan/integration.py
from __future__ import annotations

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.classify import classify_item
from loop_apidoc.plan.models import (
    Callback,
    ContractMissing,
    ContractTestCase,
    CryptoScheme,
    CryptoStep,
    CryptoVerify,
    FieldCondition,
    IntegrationContract,
    KeySource,
    NormalizationPlan,
)

_QID = "integration"
_APATH = "integration.json"


def _cite(item: dict, manifest: Manifest) -> dict:
    """Return {status, citations} kwargs for a _Cited entry from its `source`."""
    status, citation = classify_item(
        item.get("source"), query_id=_QID, answer_path=_APATH, manifest=manifest
    )
    return {"status": status, "citations": [citation]}


def _crypto(item: dict, manifest: Manifest) -> CryptoScheme:
    ks = item.get("key_source") or None
    vf = item.get("verify") or None
    steps = [
        CryptoStep(
            step=s.get("step"), desc=s.get("desc"), fields=list(s.get("fields") or [])
        )
        for s in (item.get("payload_assembly") or [])
        if isinstance(s, dict)
    ]
    return CryptoScheme(
        **_cite(item, manifest),
        name=item.get("name"),
        purpose=item.get("purpose"),
        algorithm=item.get("algorithm"),
        mode=item.get("mode"),
        padding=item.get("padding"),
        encoding=item.get("encoding"),
        key_source=KeySource(**{k: ks.get(k) for k in ("key", "iv", "note")})
        if isinstance(ks, dict)
        else None,
        payload_assembly=steps,
        verify=CryptoVerify(**{k: vf.get(k) for k in ("field", "method", "desc")})
        if isinstance(vf, dict)
        else None,
    )


def _callback(item: dict, manifest: Manifest) -> Callback:
    return Callback(
        **_cite(item, manifest),
        name=item.get("name"),
        trigger=item.get("trigger"),
        transport=item.get("transport"),
        payload_ref=item.get("payload_ref"),
        verification=item.get("verification"),
        expected_response=item.get("expected_response"),
    )


def _condition(item: dict, manifest: Manifest) -> FieldCondition:
    return FieldCondition(
        **_cite(item, manifest),
        scope=item.get("scope"),
        rule=item.get("rule"),
        when=item.get("when"),
        then_required=list(item.get("then_required") or []),
    )


def _test_case(item: dict, manifest: Manifest) -> ContractTestCase:
    return ContractTestCase(
        **_cite(item, manifest),
        name=item.get("name"),
        operation_ref=item.get("operation_ref"),
        request=item.get("request"),
        response=item.get("response"),
    )


def build_integration_contract(
    integration_json: dict | None,
    plan: NormalizationPlan,
    manifest: Manifest,
) -> IntegrationContract:
    """Convert agent-written integration.json into a cited IntegrationContract.

    Pure. Reuses already-structured plan data where the contract only references
    it (errors/environments are rendered at generate time, not re-extracted).
    A None/empty payload means the sources stated no integration mechanics —
    that is a recorded absence, never a failure.
    """
    data = integration_json or {}

    def _list(key: str) -> list[dict]:
        return [i for i in (data.get(key) or []) if isinstance(i, dict)]

    return IntegrationContract(
        version=str(data.get("version") or "1.0"),
        crypto=[_crypto(i, manifest) for i in _list("crypto")],
        callbacks=[_callback(i, manifest) for i in _list("callbacks")],
        field_conditions=[_condition(i, manifest) for i in _list("field_conditions")],
        test_cases=[_test_case(i, manifest) for i in _list("test_cases")],
        missing=[
            ContractMissing(area=str(m.get("area")), detail=str(m.get("detail")))
            for m in _list("missing")
        ],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_plan_integration_builder.py -v`
Expected: PASS (3 tests)

> If `Manifest`/`ManifestSource`/`SourceStatus` constructor kwargs in the test don't match the real models, open `loop_apidoc/manifest/models.py` and adjust the test's `_manifest()` helper to the actual fields — the production code under test does not change.

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/plan/integration.py tests/test_plan_integration_builder.py
git commit -m "feat: [plan] build cited IntegrationContract from agent JSON"
```

---

### Task 3: Wire `integration.json` through assemble onto the plan

**Files:**
- Modify: `loop_apidoc/agentcli/assemble.py` (`load_extraction_inputs` to also read optional `integration.json`; `run_assemble_pipeline` to attach the contract to the plan)
- Test: `tests/test_assemble_integration_wiring.py`

**Interfaces:**
- Consumes: `build_integration_contract(...)` from Task 2; existing `load_extraction_inputs(extraction_dir) -> (inventory, endpoint_texts)` and `run_assemble_pipeline(...)` in `loop_apidoc/agentcli/assemble.py`; `build_normalization_plan`, `persist_plan`.
- Produces: `load_extraction_inputs(extraction_dir) -> tuple[dict, list[str], dict | None]` (now returns the optional integration dict as a 3rd element; `None` when `integration.json` is absent). The pipeline sets `plan = plan.model_copy(update={"integration": contract})` **before** `persist_plan` and `generate_outputs`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assemble_integration_wiring.py
import json
from pathlib import Path

from loop_apidoc.agentcli.assemble import load_extraction_inputs


def _write(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_load_returns_integration_when_present(tmp_path: Path):
    _write(tmp_path / "inventory.json", {"title": "X", "overview": "o"})
    (tmp_path / "endpoints").mkdir()
    _write(tmp_path / "integration.json", {"crypto": [{"name": "c", "source": "s"}]})
    inventory, endpoint_texts, integration = load_extraction_inputs(tmp_path)
    assert integration["crypto"][0]["name"] == "c"


def test_load_integration_optional(tmp_path: Path):
    _write(tmp_path / "inventory.json", {"title": "X", "overview": "o"})
    (tmp_path / "endpoints").mkdir()
    inventory, endpoint_texts, integration = load_extraction_inputs(tmp_path)
    assert integration is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_assemble_integration_wiring.py -v`
Expected: FAIL — `load_extraction_inputs` returns a 2-tuple, so unpacking into 3 names raises `ValueError: not enough values to unpack`.

- [ ] **Step 3: Write minimal implementation**

In `loop_apidoc/agentcli/assemble.py`:

1. Add the import near the other plan imports:

```python
from loop_apidoc.plan.integration import build_integration_contract
```

2. Change `load_extraction_inputs` to read the optional file and return it as a 3rd element. Append, before the `return`:

```python
    integration_path = extraction_dir / "integration.json"
    integration: dict | None = None
    if integration_path.exists():
        try:
            integration = json.loads(integration_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AssembleInputError(
                f"integration.json is not valid JSON: {exc}"
            ) from exc
        if not isinstance(integration, dict):
            raise AssembleInputError("integration.json must be a JSON object")
    return inventory, endpoint_texts, integration
```

(Adjust the existing `return inventory, endpoint_texts` line to the new 3-value form. Confirm `json` and `AssembleInputError` are already imported at the top of the file — they are used by the existing inventory loader.)

3. In `run_assemble_pipeline`, update the unpack and attach the contract:

```python
    inventory, endpoint_texts, integration = load_extraction_inputs(extraction_dir)
```

then, immediately after `plan = build_normalization_plan(extraction, manifest)` and before `persist_plan(run_dir, plan)`:

```python
    contract = build_integration_contract(integration, plan, manifest)
    plan = plan.model_copy(update={"integration": contract})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_assemble_integration_wiring.py -v`
Expected: PASS (2 tests). Also run the existing assemble suite to confirm the tuple change didn't break callers:
Run: `uv run pytest tests/ -k assemble -v`
Expected: PASS (fix any other `load_extraction_inputs` unpack sites the run surfaces).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/agentcli/assemble.py tests/test_assemble_integration_wiring.py
git commit -m "feat: [assemble] read optional integration.json and attach contract to plan"
```

---

### Task 4: Emit `integration-contract.json` + provenance targets (`generate/integration.py`)

**Files:**
- Create: `loop_apidoc/generate/integration.py`
- Modify: `loop_apidoc/generate/models.py` (add `integration` field to `GenerateResult`)
- Modify: `loop_apidoc/generate/writer.py` (`build_result` + `generate_outputs`)
- Modify: `loop_apidoc/generate/provenance.py` (`build_provenance` appends integration entries)
- Test: `tests/test_generate_integration.py`

**Interfaces:**
- Consumes: `IntegrationContract` and entries from `loop_apidoc/plan/models.py`; `ProvenanceEntry`, `ProvenanceDocument` from `loop_apidoc/generate/models.py`; the existing `_entries(target, cited) -> list[ProvenanceEntry]` helper in `loop_apidoc/generate/provenance.py`; `plan.errors` (`list[ErrorEntry]`) and `plan.environments`.
- Produces:
  - `build_integration_document(plan: NormalizationPlan) -> dict | None` — the serializable contract dict (returns `None` when `plan.integration` is `None`). `error_codes` is rendered from `plan.errors` (code/meaning/http_status); `base_urls` from `plan.environments`.
  - `integration_provenance_entries(contract: IntegrationContract) -> list[ProvenanceEntry]` — one group per crypto/callback (`integration.crypto.{name}` / `integration.callbacks.{name}`), `integration.field_conditions.{index}` per condition, `integration.test_cases.{name}` per case; built via the shared `_entries` helper. **No** entry for `error_codes`.
  - `GenerateResult.integration: dict | None = None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_generate_integration.py
from loop_apidoc.generate.integration import (
    build_integration_document,
    integration_provenance_entries,
)
from loop_apidoc.plan.models import (
    Callback,
    CryptoScheme,
    ErrorEntry,
    IntegrationContract,
    NormalizationPlan,
    PlanItemStatus,
    SourceCitation,
)


def _plan_with_contract() -> NormalizationPlan:
    contract = IntegrationContract(
        crypto=[
            CryptoScheme(
                status=PlanItemStatus.SUPPORTED,
                name="TradeInfo 加密",
                algorithm="AES",
                citations=[SourceCitation(query_id="integration", answer_path="integration.json", locator="p.12")],
            )
        ],
        callbacks=[Callback(status=PlanItemStatus.SUPPORTED, name="NotifyURL")],
    )
    return NormalizationPlan(
        notebook_url="x",
        errors=[ErrorEntry(status=PlanItemStatus.SUPPORTED, code="4001", meaning="參數錯誤")],
        integration=contract,
    )


def test_document_none_when_no_contract():
    assert build_integration_document(NormalizationPlan(notebook_url="x")) is None


def test_document_renders_sections_and_reuses_errors():
    doc = build_integration_document(_plan_with_contract())
    assert doc["version"] == "1.0"
    assert doc["crypto"][0]["algorithm"] == "AES"
    assert doc["error_codes"][0]["code"] == "4001"  # reused from plan.errors


def test_provenance_targets_for_contract():
    contract = _plan_with_contract().integration
    targets = {e.target for e in integration_provenance_entries(contract)}
    assert "integration.crypto.TradeInfo 加密" in targets
    assert "integration.callbacks.NotifyURL" in targets
    # error_codes must NOT get an integration.* target
    assert not any(t.startswith("integration.error") for t in targets)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_generate_integration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.generate.integration'`

- [ ] **Step 3: Write minimal implementation**

Create `loop_apidoc/generate/integration.py`:

```python
from __future__ import annotations

from loop_apidoc.generate.models import ProvenanceEntry
from loop_apidoc.generate.provenance import _entries
from loop_apidoc.plan.models import IntegrationContract, NormalizationPlan


def _error_codes(plan: NormalizationPlan) -> list[dict]:
    return [
        {"code": e.code, "meaning": e.meaning, "http_status": e.http_status}
        for e in plan.errors
    ]


def _base_urls(plan: NormalizationPlan) -> list[dict]:
    return [
        {"name": e.name, "base_url": e.base_url, "version": e.version}
        for e in plan.environments
    ]


def build_integration_document(plan: NormalizationPlan) -> dict | None:
    """Serialize plan.integration into the integration-contract.json dict (pure).

    crypto/callbacks/field_conditions/test_cases come from the extracted
    contract; error_codes/base_urls are reused from already-structured plan data
    so the same fact is never grounded twice.
    """
    contract = plan.integration
    if contract is None:
        return None
    payload = contract.model_dump(exclude={"missing"}, exclude_none=False)
    payload["api_title"] = plan.resolved_title
    payload["base_urls"] = _base_urls(plan)
    payload["error_codes"] = _error_codes(plan)
    payload["missing"] = [m.model_dump() for m in contract.missing]
    # Drop per-entry provenance bookkeeping from the product file; provenance.json
    # carries the source mapping.
    for section in ("crypto", "callbacks", "field_conditions", "test_cases"):
        for entry in payload.get(section, []):
            entry.pop("status", None)
            entry.pop("citations", None)
    return payload


def integration_provenance_entries(
    contract: IntegrationContract,
) -> list[ProvenanceEntry]:
    """One provenance group per contract leaf (error_codes excluded — reused)."""
    out: list[ProvenanceEntry] = []
    for scheme in contract.crypto:
        out += _entries(f"integration.crypto.{scheme.name}", scheme)
    for cb in contract.callbacks:
        out += _entries(f"integration.callbacks.{cb.name}", cb)
    for idx, cond in enumerate(contract.field_conditions):
        out += _entries(f"integration.field_conditions.{idx}", cond)
    for case in contract.test_cases:
        out += _entries(f"integration.test_cases.{case.name}", case)
    return out
```

Add to `loop_apidoc/generate/models.py` `GenerateResult`:

```python
class GenerateResult(BaseModel):
    openapi: dict
    markdown: str
    provenance: ProvenanceDocument
    integration: dict | None = None
```

In `loop_apidoc/generate/provenance.py`, at the end of `build_provenance`, before it returns the `ProvenanceDocument`, append the integration entries when a contract is present:

```python
    if plan.integration is not None:
        from loop_apidoc.generate.integration import integration_provenance_entries

        entries += integration_provenance_entries(plan.integration)
```

(`entries` is the local accumulator list `build_provenance` already builds; match its real name when editing. The local import avoids a circular import between `provenance.py` and `integration.py`.)

In `loop_apidoc/generate/writer.py`:

```python
from loop_apidoc.generate.integration import build_integration_document

def build_result(plan: NormalizationPlan, manifest: Manifest) -> GenerateResult:
    return GenerateResult(
        openapi=build_openapi(plan),
        markdown=build_markdown(plan, manifest),
        provenance=build_provenance(plan),
        integration=build_integration_document(plan),
    )
```

and in `generate_outputs`, after the `provenance.json` write, add:

```python
    if result.integration is not None:
        import json

        (run_dir / "integration-contract.json").write_text(
            json.dumps(result.integration, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_generate_integration.py -v`
Expected: PASS (3 tests). Then the generate suite:
Run: `uv run pytest tests/ -k generate -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/ tests/test_generate_integration.py
git commit -m "feat: [generate] emit integration-contract.json and integration.* provenance"
```

---

### Task 5: "整合機制" section in the markdown guide

**Files:**
- Modify: `loop_apidoc/generate/markdown.py` (add header to `REQUIRED_MARKDOWN_SECTIONS`, add `_integration(plan)` helper, append to the `sections` list in `build_markdown`)
- Test: `tests/test_markdown_integration_section.py`

**Interfaces:**
- Consumes: `plan.integration` (`IntegrationContract | None`). The header and section body must be added at the **same index** so the existing zip stays aligned.
- Produces: a new required section `"## 整合機制"` rendered from the contract; when `plan.integration` is `None` or all-empty, the section body states `"（來源未提供整合機制資訊)"` so the required header is still present (consistency with the other always-present sections).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_markdown_integration_section.py
from datetime import datetime, timezone

from loop_apidoc.generate.markdown import REQUIRED_MARKDOWN_SECTIONS, build_markdown
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import (
    CryptoScheme,
    IntegrationContract,
    NormalizationPlan,
    PlanItemStatus,
)


def _manifest() -> Manifest:
    return Manifest(generated_at=datetime(2026, 6, 28, tzinfo=timezone.utc), sources=[])


def test_section_header_registered():
    assert "## 整合機制" in REQUIRED_MARKDOWN_SECTIONS


def test_section_renders_crypto():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            crypto=[CryptoScheme(status=PlanItemStatus.SUPPORTED, name="TradeInfo 加密", algorithm="AES")]
        ),
    )
    md = build_markdown(plan, _manifest())
    assert "## 整合機制" in md
    assert "TradeInfo 加密" in md
    assert "AES" in md


def test_section_placeholder_when_absent():
    plan = NormalizationPlan(notebook_url="x")
    md = build_markdown(plan, _manifest())
    assert "## 整合機制" in md
    assert "來源未提供整合機制資訊" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_markdown_integration_section.py -v`
Expected: FAIL — `"## 整合機制" not in REQUIRED_MARKDOWN_SECTIONS`

- [ ] **Step 3: Write minimal implementation**

In `loop_apidoc/generate/markdown.py`, add the header to `REQUIRED_MARKDOWN_SECTIONS` immediately **after** `"## 共用規則"` (so integration mechanics sit with the shared-rules area, before per-endpoint detail):

```python
REQUIRED_MARKDOWN_SECTIONS: tuple[str, ...] = (
    "## 文件範圍與來源",
    "## 串接前置條件",
    "## 環境與 base URL",
    "## 驗證／授權",
    "## 共用規則",
    "## 整合機制",
    "## Endpoint",
    "## Request／Response 範例",
    "## 錯誤碼",
    "## 限制與注意事項",
    "## 已知缺漏與來源衝突",
)
```

Add the helper (near the other `_section` helpers):

```python
def _integration(plan: NormalizationPlan) -> list[str]:
    contract = plan.integration
    if contract is None or not (
        contract.crypto or contract.callbacks or contract.field_conditions or contract.test_cases
    ):
        return ["（來源未提供整合機制資訊)"]
    lines: list[str] = []
    for c in contract.crypto:
        lines.append(f"### 加解密／簽章：{c.name or '(未命名)'}")
        if c.algorithm:
            lines.append(f"- 演算法：{c.algorithm}{f'/{c.mode}' if c.mode else ''}")
        if c.key_source and (c.key_source.key or c.key_source.iv):
            lines.append(f"- 金鑰來源：key={c.key_source.key}, iv={c.key_source.iv}")
        for s in c.payload_assembly:
            lines.append(f"  {s.step}. {s.desc or ''}")
        if c.verify and c.verify.field:
            lines.append(f"- 驗章：{c.verify.field}（{c.verify.method or ''}）")
    for cb in contract.callbacks:
        lines.append(f"### 回呼：{cb.name or '(未命名)'}")
        if cb.expected_response:
            lines.append(f"- 需回應：{cb.expected_response}")
        if cb.verification:
            lines.append(f"- 驗證：{cb.verification}")
    for fc in contract.field_conditions:
        if fc.rule:
            lines.append(f"- 條件：{fc.rule}")
    return lines
```

In `build_markdown`, insert `_integration(plan)` into the `sections` list at the **same position** as the new header (between `_security(...)`/`_schemas(...)` per the actual current order — it must occupy index 5, right after `"## 共用規則"`'s body). Concretely, the `sections` list becomes:

```python
    sections = [
        _scope(plan, manifest),
        ["完成串接前，請先確認已取得 Notebook 對應的來源並完成驗證設定。"],
        _environments(plan),
        _security(plan),
        _schemas(plan),
        _integration(plan),   # NEW — aligns with "## 整合機制"
        _endpoints(plan),
        _examples(plan),
        _errors(plan),
        _operational(plan),
        _gaps(plan),
    ]
```

> Verify the current `sections` list order in the file before editing — the header tuple and this list are zipped by index, so the new entry must sit at the exact index of `"## 整合機制"`. The `"## 共用規則"` body in the live code maps to `_schemas(plan)`; insert `_integration` directly after it.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_markdown_integration_section.py -v`
Expected: PASS (3 tests). Then the full markdown suite to confirm section alignment didn't shift:
Run: `uv run pytest tests/ -k markdown -v`
Expected: PASS (update any test asserting the section count/order to include the new section).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/markdown.py tests/test_markdown_integration_section.py
git commit -m "feat: [generate] add 整合機制 section to api-guide"
```

---

### Task 6: Contract validation (`validate/integration.py`)

**Files:**
- Create: `loop_apidoc/validate/integration.py`
- Modify: `loop_apidoc/validate/validator.py` (`validate_outputs` calls the new check)
- Test: `tests/test_validate_integration.py`

**Interfaces:**
- Consumes: `Issue`, `IssueCode`, `Severity` from `loop_apidoc/validate/models.py`; `NormalizationPlan`, `IntegrationContract`, `PlanItemStatus` from `loop_apidoc/plan/models.py`; `GenerateResult` from `loop_apidoc/generate/models.py` (for OpenAPI ref resolution).
- Produces: `check_integration(plan: NormalizationPlan, result: GenerateResult) -> list[Issue]`, enforcing three rules:
  1. **No-speculation:** any crypto/callback/field_condition/test_case entry with empty `citations` → `UNSUPPORTED_ASSERTION`.
  2. **Reference resolution:** `callbacks.payload_ref` (`schemas.{name}`) and `test_cases.operation_ref` (`paths.{path}.{method}`) that don't resolve against `result.openapi` → `OUTPUT_MISMATCH` (auto_fixable=True).
  3. **Signal-word gap:** if `plan.operational`/`plan.security_schemes` text contains an encryption/signature signal word (`加密`, `簽章`, `AES`, `HashKey`, `HashIV`, `SHA256`) but the contract has **no** crypto scheme → `REQUIRED_INFO_MISSING`.
  - `check_integration` returns `[]` when `plan.integration is None` **and** no signal words are present (a source with no mechanics is valid).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validate_integration.py
from loop_apidoc.generate.models import GenerateResult, ProvenanceDocument
from loop_apidoc.plan.models import (
    Callback,
    CryptoScheme,
    ContractTestCase,
    IntegrationContract,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SecuritySchemeEntry,
    SourceCitation,
)
from loop_apidoc.validate.integration import check_integration
from loop_apidoc.validate.models import IssueCode


def _result(openapi: dict) -> GenerateResult:
    return GenerateResult(openapi=openapi, markdown="", provenance=ProvenanceDocument(notebook_url="x"))


def _cited(**kw):
    return dict(status=PlanItemStatus.SUPPORTED, citations=[SourceCitation(query_id="i", answer_path="i")], **kw)


def test_uncited_crypto_is_unsupported_assertion():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[CryptoScheme(status=PlanItemStatus.UNVERIFIED, name="c")]),
    )
    codes = [i.code for i in check_integration(plan, _result({}))]
    assert IssueCode.UNSUPPORTED_ASSERTION in codes


def test_dangling_operation_ref_is_output_mismatch():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            test_cases=[ContractTestCase(**_cited(name="t", operation_ref="paths./ghost.post"))]
        ),
    )
    codes = [i.code for i in check_integration(plan, _result({"paths": {}}))]
    assert IssueCode.OUTPUT_MISMATCH in codes


def test_resolvable_operation_ref_ok():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            test_cases=[ContractTestCase(**_cited(name="t", operation_ref="paths./mpg.post"))]
        ),
    )
    openapi = {"paths": {"/mpg": {"post": {}}}}
    codes = [i.code for i in check_integration(plan, _result(openapi))]
    assert IssueCode.OUTPUT_MISMATCH not in codes


def test_signal_word_without_crypto_is_required_info_missing():
    plan = NormalizationPlan(
        notebook_url="x",
        operational=[OperationalEntry(status=PlanItemStatus.SUPPORTED, topic="安全", detail="請以 AES 加密 TradeInfo")],
        integration=IntegrationContract(),
    )
    codes = [i.code for i in check_integration(plan, _result({}))]
    assert IssueCode.REQUIRED_INFO_MISSING in codes


def test_no_mechanics_no_signal_is_clean():
    plan = NormalizationPlan(notebook_url="x")
    assert check_integration(plan, _result({})) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_validate_integration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.validate.integration'`

- [ ] **Step 3: Write minimal implementation**

```python
# loop_apidoc/validate/integration.py
from __future__ import annotations

from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.plan.models import IntegrationContract, NormalizationPlan
from loop_apidoc.validate.models import Issue, IssueCode, Severity

_SIGNAL_WORDS = ("加密", "簽章", "AES", "HashKey", "HashIV", "SHA256")


def _issue(code: IssueCode, location: str, evidence: str, fix: str, *, fixable: bool = False) -> Issue:
    return Issue(
        code=code,
        severity=Severity.ERROR,
        location=location,
        evidence=evidence,
        suggested_fix=fix,
        auto_fixable=fixable,
    )


def _uncited(contract: IntegrationContract) -> list[Issue]:
    issues: list[Issue] = []
    groups = (
        ("crypto", contract.crypto),
        ("callbacks", contract.callbacks),
        ("field_conditions", contract.field_conditions),
        ("test_cases", contract.test_cases),
    )
    for section, entries in groups:
        for idx, entry in enumerate(entries):
            if not entry.citations:
                label = getattr(entry, "name", None) or str(idx)
                issues.append(
                    _issue(
                        IssueCode.UNSUPPORTED_ASSERTION,
                        f"integration.{section}.{label}",
                        "契約條目無任何來源引用",
                        "為此條目補上來源引用,或在無來源時移除",
                    )
                )
    return issues


def _refs(contract: IntegrationContract, openapi: dict) -> list[Issue]:
    issues: list[Issue] = []
    paths = openapi.get("paths") or {}
    schemas = ((openapi.get("components") or {}).get("schemas")) or {}
    for cb in contract.callbacks:
        ref = cb.payload_ref
        if ref and ref.startswith("schemas.") and ref.split("schemas.", 1)[1] not in schemas:
            issues.append(
                _issue(
                    IssueCode.OUTPUT_MISMATCH,
                    f"integration.callbacks.{cb.name}",
                    f"payload_ref 指向不存在的 schema:{ref}",
                    "更正 payload_ref 或補上對應 schema",
                    fixable=True,
                )
            )
    for case in contract.test_cases:
        ref = case.operation_ref
        if ref and ref.startswith("paths."):
            body = ref.split("paths.", 1)[1]
            path, _, method = body.rpartition(".")
            if path not in paths or method not in (paths.get(path) or {}):
                issues.append(
                    _issue(
                        IssueCode.OUTPUT_MISMATCH,
                        f"integration.test_cases.{case.name}",
                        f"operation_ref 指向不存在的 operation:{ref}",
                        "更正 operation_ref 至既有 paths.{path}.{method}",
                        fixable=True,
                    )
                )
    return issues


def _signal_gap(plan: NormalizationPlan, contract: IntegrationContract | None) -> list[Issue]:
    text = " ".join(
        [e.detail or "" for e in plan.operational]
        + [s.details or "" for s in plan.security_schemes]
    )
    hit = next((w for w in _SIGNAL_WORDS if w in text), None)
    has_crypto = bool(contract and contract.crypto)
    if hit and not has_crypto:
        return [
            _issue(
                IssueCode.REQUIRED_INFO_MISSING,
                "integration.crypto",
                f"來源出現「{hit}」訊號詞,但契約未抽到任何加解密/簽章機制",
                "重讀相關來源段落,補上 crypto 細節後重跑 assemble",
            )
        ]
    return []


def check_integration(plan: NormalizationPlan, result: GenerateResult) -> list[Issue]:
    """Validate the integration contract: no-speculation + ref resolution + signal-word gap."""
    contract = plan.integration
    issues: list[Issue] = []
    if contract is not None:
        issues += _uncited(contract)
        issues += _refs(contract, result.openapi)
    issues += _signal_gap(plan, contract)
    return issues
```

Wire into `loop_apidoc/validate/validator.py`:

```python
from loop_apidoc.validate.integration import check_integration
```

and inside `validate_outputs`, add:

```python
    issues += check_integration(plan, result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_validate_integration.py -v`
Expected: PASS (5 tests). Then the validate suite:
Run: `uv run pytest tests/ -k validate -v`
Expected: PASS

> If `Issue`/`Severity` field names differ from those used here, open `loop_apidoc/validate/models.py` and match the real field names — the check logic is unchanged.

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/validate/ tests/test_validate_integration.py
git commit -m "feat: [validate] integration contract no-speculation, ref-resolution, signal-word checks"
```

---

### Task 7: SKILL.md — integration extraction subagent + `integration.json` contract

**Files:**
- Modify: `skills/loop-apidoc/SKILL.md`
- Test: none (documentation). Verification is the e2e run in Task 8.

**Interfaces:**
- Consumes: the agent fan-out section (subagent contract, lines ~43–96) and the correction-loop section (lines ~105–112).
- Produces: a new read-only subagent that writes `integration.json` with the shape below, plus a correction-loop note for `REQUIRED_INFO_MISSING` on `integration.crypto`.

- [ ] **Step 1: Add the integration extraction subagent**

After the endpoint-detail subagent description, add a new subagent block. It must reuse the existing grounding rule ("Fill strictly from the sources … Never infer … Return only the JSON object"). Document the `integration.json` shape verbatim:

````markdown
### Integration mechanics subagent (writes `integration.json`)

Dispatch one read-only subagent to read the sections describing encryption,
signing, callbacks, and cross-field conditions. It returns **only** this JSON
object (no prose, no file writes); you write it to `integration.json` beside
`inventory.json`. Anything the sources do not state → `null` and add a label to
`missing`. Never infer crypto/callback details from REST/payment conventions.

```json
{
  "version": "1.0",
  "crypto": [
    {
      "name": "str",
      "purpose": "request|response|callback|signature|null",
      "algorithm": "str|null",
      "mode": "str|null",
      "padding": "str|null",
      "encoding": "str|null",
      "key_source": {"key": "str|null", "iv": "str|null", "note": "str|null"},
      "payload_assembly": [{"step": 1, "desc": "str", "fields": ["str"]}],
      "verify": {"field": "str|null", "method": "str|null", "desc": "str|null"},
      "source": "str"
    }
  ],
  "callbacks": [
    {
      "name": "str",
      "trigger": "str|null",
      "transport": "str|null",
      "payload_ref": "schemas.{name}|null",
      "verification": "str|null",
      "expected_response": "str|null",
      "source": "str"
    }
  ],
  "field_conditions": [
    {"scope": "str|null", "rule": "str", "when": "str|null", "then_required": ["str"], "source": "str"}
  ],
  "test_cases": [
    {"name": "str", "operation_ref": "paths.{path}.{method}|null", "request": {}, "response": {}, "source": "str"}
  ],
  "missing": [{"area": "str", "detail": "str"}]
}
```

- `payload_assembly`: the ordered steps for building the string to encrypt/sign
  (the signature chain). Only include what the source states.
- `payload_ref` / `operation_ref`: point to an existing `inventory.schemas` name
  or `paths.{path}.{method}`; `null` if no match.
- `source`: required per entry — cites the source section/page/URL.
- If the sources describe **no** integration mechanics, omit `integration.json`
  entirely (do not write an empty file).
````

- [ ] **Step 2: Add the correction-loop note**

In the correction-loop section, add a bullet:

```markdown
- On `REQUIRED_INFO_MISSING` at `integration.crypto`: the source mentions
  encryption/signing but no crypto detail was extracted — re-read the relevant
  section and overwrite `integration.json`, then re-run assemble.
- On `OUTPUT_MISMATCH` at `integration.*`: a `payload_ref`/`operation_ref` does
  not resolve — fix the reference to an existing schema/operation.
```

- [ ] **Step 3: Verify the contract shape matches the builder**

Read `loop_apidoc/plan/integration.py` (Task 2) and confirm every JSON key in the SKILL doc maps to a field the builder reads. Cross-check `crypto`, `callbacks`, `field_conditions`, `test_cases`, `missing`.

- [ ] **Step 4: Commit**

```bash
git add skills/loop-apidoc/SKILL.md
git commit -m "docs: [skill] integration mechanics subagent + integration.json contract"
```

---

### Task 8: End-to-end verification on a real payment source

**Files:**
- Test: manual e2e (no new automated test file); optionally add a fixture-based assemble test if a small JSON fixture is practical.

**Interfaces:**
- Consumes: the full `assemble` pipeline with an `integration.json` present.

- [ ] **Step 1: Run the full test suite + lint**

Run: `uv run pytest`
Expected: all PASS.
Run: `uv run ruff check .`
Expected: no errors.

- [ ] **Step 2: Hand-craft a minimal extraction dir and run assemble**

Create a scratch extraction dir with `inventory.json`, an `endpoints/` dir, and an `integration.json` carrying one crypto scheme (with `payload_assembly`), one callback, and one test_case. Run the `assemble` CLI against it (see `CLAUDE.md` for the exact invocation form: `uv run loop-apidoc assemble ...` or the plugin form). Confirm the run dir contains `integration-contract.json`.

- [ ] **Step 3: Human-eye verification (per project lesson)**

Open the produced `integration-contract.json` and `api-guide.zh-TW.md`. Confirm by eye:
- the crypto `payload_assembly` reproduces the source's signature-chain order,
- `provenance.json` contains `integration.crypto.*` / `integration.callbacks.*` targets,
- the "整合機制" guide section reads correctly,
- a deliberately dangling `operation_ref` produces an `OUTPUT_MISMATCH` in `validation/report.md`.

> Validation PASS ≠ good product (project lesson). The signature chain must be inspected by eye, not just asserted by the suite.

- [ ] **Step 4: Final commit (if fixtures/docs added)**

```bash
git add -A
git commit -m "test: [e2e] integration-contract end-to-end verification"
```

---

## Self-Review notes

- **Spec coverage:** §3 architecture → Tasks 3–6; §4 schema → Tasks 1–2,4; §5 provenance/validation → Tasks 4,6; §6 package boundaries → all tasks follow the table; §7 products → Task 4 (json) + Task 5 (guide); §8 testing → each task is TDD, Task 8 is the e2e. error_codes-reuse-no-target → Task 4 test `test_provenance_targets_for_contract`.
- **Out of scope (spec §9):** extraction strong-typing, other dev-facing products, non-contract codegen-readiness — not in this plan.
- **Type consistency:** entry classes subclass `_Cited` (status+citations), so `generate/provenance.py::_entries` and the no-speculation pattern work unchanged; `build_integration_contract` returns `IntegrationContract`; `GenerateResult.integration` is `dict | None`; `check_integration(plan, result)` signature is stable across Tasks 6 and the validator wiring.
