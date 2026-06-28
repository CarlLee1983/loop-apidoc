# 簽章接回 request 欄位 + 驗證 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 `build_examples` 把 `sign()` 簽章值明確接回 request 的 body/header 目標欄位,並讓驗證能偵測「能接卻漏接」與「來源未指明目標欄位」。

**Architecture:** 在 `generate/examples.py` 既有 `(shape, schemes)` 渲染管線中,新增接回輔助(`_wire_target` / `_payload_field_names` / `_func_name`)與三語接回片段(curl 僅註解);在 `validate/integration.py` 的 `check_integration` 掃描 `result.examples` 做事後交叉檢查。全部 fail-closed,不臆測 payload 精確組法。

**Tech Stack:** Python 3.11+、pydantic v2、pytest、typer、ruff。

## Global Constraints

- 來源是唯一真實依據;未說明者留 placeholder/gap,不臆測(不變式)。
- payload 確切串接/排序為來源特定散文,**不偽裝精確**;`k=v` 以 `&` 連僅為示意並加註解。
- 目標欄位來源固定為 `CryptoScheme.verify.field`,不新增模型欄位。
- 簽章函式名沿用 `sign`(單一)/`sign_<snake(name)>`(多個)規則。
- 純函式邊界不變:只有 `generate/` 與 `run/` 寫檔;`examples.py` / `integration.py` 維持純函式。
- Python `>=3.11`,以 `uv` 執行(`uv run pytest` / `uv run ruff check .`)。

---

### Task 1: examples.py — 簽章接回三語片段

**Files:**
- Modify: `loop_apidoc/generate/examples.py`
- Test: `tests/test_generate_examples.py`

**Interfaces:**
- Consumes: 既有 `_snake`、`_signature_explicit`、`_is_cbc`、`CryptoScheme`、`shape` dict（keys: `body`/`header` 為 `list[tuple[name, kind, value]]`）。
- Produces:
  - `_func_name(scheme: CryptoScheme, idx: int, total: int) -> str`
  - `_wire_target(scheme: CryptoScheme, shape: dict) -> tuple[str, str] | None`（回 `(location, field)`，`location ∈ {"body","header"}`）
  - `_payload_field_names(scheme: CryptoScheme, shape: dict, target: str) -> list[str]`
  - `_ts_wiring(shape: dict, schemes: list[CryptoScheme]) -> list[str]`
  - `_py_wiring(shape: dict, schemes: list[CryptoScheme]) -> list[str]`
  - 模組常數 `_PAYLOAD_NOTE`、`_PAYLOAD_GAP`
  - `_render_ts` / `_render_py` / `_render_curl` 輸出在可接回時含接回行。

- [ ] **Step 1: 寫失敗測試（接回輔助 + 三語接回）**

加到 `tests/test_generate_examples.py` 末尾:

```python
# --- 簽章接回 request 欄位 ---

from loop_apidoc.plan.models import CryptoVerify, KeySource


def _runnable_scheme(target="CheckMacValue", fields=("MerchantID", "Amount")):
    return CryptoScheme(
        status="supported", name="CheckValue", purpose="request",
        algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "排序欄位後加密", "fields": list(fields)}],
        verify=CryptoVerify(field=target, method="AES", desc="比對簽章"),
    )


def _sig_shape():
    return _shape(
        body=[
            ("MerchantID", "placeholder", "<merchant_id>"),
            ("Amount", "placeholder", "<amount>"),
            ("CheckMacValue", "placeholder", "<check_mac_value>"),
        ],
        content_type="application/x-www-form-urlencoded",
    )


def test_wire_target_resolves_body_field():
    from loop_apidoc.generate.examples import _wire_target
    assert _wire_target(_runnable_scheme(), _sig_shape()) == ("body", "CheckMacValue")


def test_wire_target_none_when_field_absent_in_request():
    from loop_apidoc.generate.examples import _wire_target
    assert _wire_target(_runnable_scheme(target="NotThere"), _sig_shape()) is None


def test_wire_target_none_when_no_verify_field():
    from loop_apidoc.generate.examples import _wire_target
    s = _runnable_scheme()
    s = s.model_copy(update={"verify": None})
    assert _wire_target(s, _sig_shape()) is None


def test_wire_target_none_when_not_runnable():
    from loop_apidoc.generate.examples import _wire_target
    s = CryptoScheme(status="supported", name="x", verify=CryptoVerify(field="CheckMacValue"))
    assert _wire_target(s, _sig_shape()) is None


def test_payload_field_names_intersects_body_and_excludes_target():
    from loop_apidoc.generate.examples import _payload_field_names
    s = _runnable_scheme(fields=("MerchantID", "Amount", "CheckMacValue", "Ghost"))
    names = _payload_field_names(s, _sig_shape(), "CheckMacValue")
    assert names == ["MerchantID", "Amount"]  # 交集 body、去掉 target 與不存在欄位


def test_render_ts_wires_signature_into_body():
    from loop_apidoc.generate.examples import _render_ts
    out = _render_ts(_sig_shape(), [_runnable_scheme()])
    assert "createCipheriv" in out
    assert "請依 payload_assembly 核對" in out
    assert "[\"MerchantID\", \"Amount\"]" in out
    assert "[\"CheckMacValue\"] = sign(payload)" in out


def test_render_py_wires_signature_into_body():
    from loop_apidoc.generate.examples import _render_py
    out = _render_py(_sig_shape(), [_runnable_scheme()])
    assert "def sign" in out
    assert "sig_payload = " in out
    assert 'payload["CheckMacValue"] = sign(sig_payload)' in out


def test_render_py_wiring_empty_fields_uses_placeholder_but_still_wires():
    from loop_apidoc.generate.examples import _render_py
    s = _runnable_scheme(fields=())
    out = _render_py(_sig_shape(), [s])
    assert "來源未列出簽章欄位" in out
    assert 'payload["CheckMacValue"] = sign(sig_payload)' in out


def test_render_curl_notes_target_field_but_does_not_wire():
    from loop_apidoc.generate.examples import _render_curl
    out = _render_curl(_sig_shape(), [_runnable_scheme()])
    assert "簽章值請填回欄位：CheckMacValue" in out
    assert "= sign(" not in out  # curl 不接回


def test_render_ts_wires_into_header_when_target_is_header():
    from loop_apidoc.generate.examples import _render_ts
    shape = _shape(
        header=[("X-Signature", "placeholder", "<x_signature>")],
        body=[("Amount", "placeholder", "<amount>")],
        content_type="application/json",
    )
    s = _runnable_scheme(target="X-Signature", fields=("Amount",))
    out = _render_ts(shape, [s])
    assert "(headers as any)[\"X-Signature\"] = sign(payload)" in out


def test_no_wiring_when_scheme_has_no_verify_field():
    # 既有行為回歸:無 verify.field 的可跑 scheme 不接回(只渲染 sign 函式)
    from loop_apidoc.generate.examples import _render_py
    s = _runnable_scheme().model_copy(update={"verify": None})
    out = _render_py(_sig_shape(), [s])
    assert "def sign" in out
    assert "= sign(sig_payload)" not in out
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_generate_examples.py -k "wire or wiring or notes_target or no_wiring or payload_field" -v`
Expected: FAIL（`ImportError: cannot import name '_wire_target'` 等）。

- [ ] **Step 3: 實作輔助與接回片段**

在 `loop_apidoc/generate/examples.py`，於 `_is_cbc` 之後加入:

```python
_PAYLOAD_NOTE = "簽章 payload：來源指定下列欄位進入簽章（確切串接/排序為示意，請依 payload_assembly 核對 source）"
_PAYLOAD_GAP = "<payload：來源未列出簽章欄位，請依 payload_assembly 組裝>"


def _func_name(scheme: CryptoScheme, idx: int, total: int) -> str:
    """Signature function name; unique per scheme only when more than one exists.
    Mirrors the naming used by _ts_signature / _py_signature."""
    if total > 1:
        return f"sign_{_snake(scheme.name or str(idx))}"
    return "sign"


def _wire_target(scheme: CryptoScheme, shape: dict) -> tuple[str, str] | None:
    """If this runnable scheme's signature value should be written back into the
    request, return (location, field_name); else None.

    location is 'body' or 'header'. Wiring happens only when the scheme is runnable
    (explicit + CBC) AND verify.field names a body field or header present in this
    request — otherwise keep comment-only / gap behavior (no fabrication)."""
    if not (_signature_explicit(scheme) and _is_cbc(scheme)):
        return None
    target = scheme.verify.field if scheme.verify else None
    if not target:
        return None
    if target in [n for n, _k, _v in shape["body"]]:
        return ("body", target)
    if target in [n for n, _k, _v in shape["header"]]:
        return ("header", target)
    return None


def _payload_field_names(scheme: CryptoScheme, shape: dict, target: str) -> list[str]:
    """Body field names the source says enter the signature payload: union of
    payload_assembly[].fields ∩ this request's body fields, excluding the target."""
    body_names = [n for n, _k, _v in shape["body"]]
    names: list[str] = []
    for step in scheme.payload_assembly:
        for f in step.fields:
            if f in body_names and f != target and f not in names:
                names.append(f)
    return names


def _ts_wiring(shape: dict, schemes: list[CryptoScheme]) -> list[str]:
    lines: list[str] = []
    total = len(schemes)
    for idx, s in enumerate(schemes):
        wire = _wire_target(s, shape)
        if wire is None:
            continue
        loc, target = wire
        obj = "body" if loc == "body" else "headers"
        fn = _func_name(s, idx, total)
        pvar = "payload" if total == 1 else f"payload_{_snake(s.name or str(idx))}"
        fields = _payload_field_names(s, shape, target)
        lines.append(f"// {_PAYLOAD_NOTE}")
        if fields:
            arr = ", ".join(json.dumps(f, ensure_ascii=False) for f in fields)
            lines.append(
                f"const {pvar} = [{arr}].map((k) => `${{k}}=${{({obj} as any)[k]}}`).join('&')"
            )
        else:
            lines.append(f"const {pvar} = {json.dumps(_PAYLOAD_GAP, ensure_ascii=False)}")
        lines.append(
            f";({obj} as any)[{json.dumps(target, ensure_ascii=False)}] = {fn}({pvar})"
        )
    return lines


def _py_wiring(shape: dict, schemes: list[CryptoScheme]) -> list[str]:
    lines: list[str] = []
    total = len(schemes)
    for idx, s in enumerate(schemes):
        wire = _wire_target(s, shape)
        if wire is None:
            continue
        loc, target = wire
        obj = "payload" if loc == "body" else "headers"
        fn = _func_name(s, idx, total)
        pvar = "sig_payload" if total == 1 else f"sig_payload_{_snake(s.name or str(idx))}"
        fields = _payload_field_names(s, shape, target)
        lines.append(f"# {_PAYLOAD_NOTE}")
        if fields:
            arr = ", ".join(json.dumps(f, ensure_ascii=False) for f in fields)
            lines.append(f'{pvar} = "&".join(f"{{k}}={{{obj}[k]}}" for k in [{arr}])')
        else:
            lines.append(f"{pvar} = {json.dumps(_PAYLOAD_GAP, ensure_ascii=False)}")
        lines.append(f"{obj}[{json.dumps(target, ensure_ascii=False)}] = {fn}({pvar})")
    return lines
```

在 `_render_curl` 中，於 signature 註解區塊之後（`url = _interpolate_path(...)` 之前）加入目標欄位提示:

```python
    targets = [w[1] for s in schemes if (w := _wire_target(s, shape))]
    if targets:
        parts += [_comment("簽章值請填回欄位：" + ", ".join(targets)), ""]
```

在 `_render_ts` 中，於 `target = "url + '?' + params" ...` 之前加入:

```python
    lines += _ts_wiring(shape, schemes)
```

在 `_render_py` 中，於 `lines.append(f"resp = httpx.request(...)")` 之前加入:

```python
    lines += _py_wiring(shape, schemes)
```

（可選 DRY）將 `_ts_signature` / `_py_signature` 內聯的 func_name 計算改呼叫
`_func_name(s, idx, len(schemes))`，行為不變。

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_generate_examples.py -v`
Expected: PASS（新測試全過，既有測試不破——既有測試多數未設 `verify.field`）。

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/examples.py tests/test_generate_examples.py
git commit -m "feat: [generate] 簽章值接回 request 目標欄位(verify.field)，curl 維持註解"
```

---

### Task 2: validate — 偵測範例是否真用簽章流程

**Files:**
- Modify: `loop_apidoc/validate/integration.py`
- Test: `tests/test_validate_integration.py`

**Interfaces:**
- Consumes: `result.examples`（`dict[str,str]`）、`_request_signing_schemes`/`_signature_explicit`/`_is_cbc`（from `generate.examples`）、`CryptoScheme.verify.field`。
- Produces: `check_integration` 額外回傳 `OUTPUT_MISMATCH`（情境 A）與 `REQUIRED_INFO_MISSING`（情境 B）issues。

- [ ] **Step 1: 寫失敗測試**

加到 `tests/test_validate_integration.py` 末尾:

```python
# --- 範例簽章接回驗證 ---

from loop_apidoc.plan.models import CryptoVerify, KeySource


def _runnable_crypto(field):
    return CryptoScheme(
        status=PlanItemStatus.SUPPORTED,
        citations=[SourceCitation(query_id="i", answer_path="i")],
        name="CheckValue", purpose="request",
        algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "組字串", "fields": ["Amount"]}],
        verify=CryptoVerify(field=field) if field else None,
    )


def _result_with_examples(examples: dict) -> GenerateResult:
    return GenerateResult(
        openapi={}, markdown="",
        provenance=ProvenanceDocument(notebook_url="x"),
        examples=examples,
    )


def test_runnable_without_verify_field_is_required_info_missing():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[_runnable_crypto(field=None)]),
    )
    codes = [i.code for i in check_integration(plan, _result_with_examples({}))]
    assert IssueCode.REQUIRED_INFO_MISSING in codes


def test_example_uses_target_but_not_wired_is_output_mismatch():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[_runnable_crypto(field="CheckMacValue")]),
    )
    # 範例含目標欄位作為 body key,但沒有 = sign(...) 接回 → 生成器漏接
    examples = {"examples/Pay/request.py": 'payload = {\n    "CheckMacValue": "<x>",\n}\n'}
    issues = check_integration(plan, _result_with_examples(examples))
    mism = [i for i in issues if i.code is IssueCode.OUTPUT_MISMATCH]
    assert mism and mism[0].location == "examples/Pay/request.py"


def test_example_properly_wired_is_clean():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[_runnable_crypto(field="CheckMacValue")]),
    )
    examples = {
        "examples/Pay/request.py": (
            'payload = {\n    "CheckMacValue": "<x>",\n}\n'
            'sig_payload = "&".join(...)\n'
            'payload["CheckMacValue"] = sign(sig_payload)\n'
        )
    }
    codes = [i.code for i in check_integration(plan, _result_with_examples(examples))]
    assert IssueCode.OUTPUT_MISMATCH not in codes


def test_curl_not_checked_for_wiring():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[_runnable_crypto(field="CheckMacValue")]),
    )
    # 只有 curl 用到欄位且不接回 → 不應報 OUTPUT_MISMATCH
    examples = {"examples/Pay/request.sh": "curl ... CheckMacValue=<x>"}
    codes = [i.code for i in check_integration(plan, _result_with_examples(examples))]
    assert IssueCode.OUTPUT_MISMATCH not in codes
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_validate_integration.py -k "required_info_missing or output_mismatch or properly_wired or curl_not_checked" -v`
Expected: FAIL（情境 A/B 尚未實作，斷言不成立）。

- [ ] **Step 3: 實作驗證**

在 `loop_apidoc/validate/integration.py` 頂部 import 後加入:

```python
import re

from loop_apidoc.generate.examples import (
    _is_cbc,
    _request_signing_schemes,
    _signature_explicit,
)
```

加入函式:

```python
def _signature_wiring(plan: NormalizationPlan, result: GenerateResult) -> list[Issue]:
    """情境 A：可跑簽章+有目標欄位，但 ts/py 範例用到該欄位卻沒接回 → OUTPUT_MISMATCH。
    情境 B：可跑簽章但來源未指明 verify.field → REQUIRED_INFO_MISSING。curl 不檢查。"""
    issues: list[Issue] = []
    examples = result.examples or {}
    for idx, s in enumerate(_request_signing_schemes(plan)):
        if not (_signature_explicit(s) and _is_cbc(s)):
            continue
        label = s.name or str(idx)
        target = s.verify.field if s.verify else None
        if not target:
            issues.append(
                _issue(
                    IssueCode.REQUIRED_INFO_MISSING,
                    f"integration.crypto.{label}",
                    "可生成可跑簽章但來源未指明簽章值的目標欄位(verify.field)",
                    "重讀來源補上 verify.field 後重跑 assemble",
                )
            )
            continue
        wired = re.compile(r"\[['\"]" + re.escape(target) + r"['\"]\]\s*=\s*sign")
        for path, content in examples.items():
            if not (path.endswith("request.ts") or path.endswith("request.py")):
                continue
            if target not in content:
                continue
            if not wired.search(content):
                issues.append(
                    _issue(
                        IssueCode.OUTPUT_MISMATCH,
                        path,
                        f"範例用到欄位「{target}」但未接回簽章值(缺 {target}=sign(...))",
                        "重新產生範例使其將 sign() 結果接回該欄位",
                        fixable=True,
                    )
                )
    return issues
```

在 `check_integration` 結尾、`return issues` 之前加入:

```python
    issues += _signature_wiring(plan, result)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_validate_integration.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/validate/integration.py tests/test_validate_integration.py
git commit -m "feat: [validate] 偵測範例未接回簽章值(A=OUTPUT_MISMATCH)/缺目標欄位(B=REQUIRED_INFO_MISSING)"
```

---

### Task 3: CLI help 補選用 integration.json

**Files:**
- Modify: `loop_apidoc/cli.py:90-94`

**Interfaces:**
- Produces: `assemble --extraction` help 文字含 `選用 integration.json`。

- [ ] **Step 1: 改 help 文字**

把 `loop_apidoc/cli.py` 中:

```python
    extraction: Path = typer.Option(
        ..., "--extraction",
        help="agent 產出的擷取目錄(inventory.json + endpoints/*.json)",
```

改為:

```python
    extraction: Path = typer.Option(
        ..., "--extraction",
        help="agent 產出的擷取目錄(inventory.json + endpoints/*.json,選用 integration.json)",
```

- [ ] **Step 2: 驗證 help 文字**

Run: `uv run loop-apidoc assemble --help`
Expected: `--extraction` 說明含「選用 integration.json」。

- [ ] **Step 3: Commit**

```bash
git add loop_apidoc/cli.py
git commit -m "docs: [cli] assemble --extraction help 補選用 integration.json"
```

---

### Task 4: 全量回歸 + lint

**Files:** （無新增）

- [ ] **Step 1: 跑全套測試**

Run: `uv run pytest`
Expected: PASS。若 `test_generate_examples_two_source.py` / `test_generate_writer_examples.py` 因新接回行斷言失敗，檢視該案例的 scheme 是否含 `verify.field`；若是預期行為變動，更新斷言以涵蓋接回行（不可為了綠燈刪掉接回驗證）。

- [ ] **Step 2: Lint**

Run: `uv run ruff check .`
Expected: All checks passed。

- [ ] **Step 3: Commit（若有測試更新）**

```bash
git add -A
git commit -m "test: 更新範例回歸以涵蓋簽章接回行"
```

---

## Self-Review

- **Spec coverage:** A 接回邏輯（Task 1：`_wire_target`/`_payload_field_names`/三語）✓;B 驗證（Task 2：A=OUTPUT_MISMATCH、B=REQUIRED_INFO_MISSING、curl 不檢查）✓;C 測試（Task 1/2 含新測試 + Task 4 回歸）✓;D CLI help（Task 3）✓;YAGNI（不新增模型欄位、curl 不偽造）✓。
- **Placeholder scan:** 無 TBD/TODO;每個 code step 均含完整程式碼。
- **Type consistency:** `_wire_target` 回 `(location, field)`、`_func_name(scheme, idx, total)`、`_payload_field_names(scheme, shape, target)`、`_signature_wiring(plan, result)` 於 Task 1/2 一致;驗證 regex `\]\s*=\s*sign` 同時涵蓋 `sign(` 與 `sign_<name>(`。
