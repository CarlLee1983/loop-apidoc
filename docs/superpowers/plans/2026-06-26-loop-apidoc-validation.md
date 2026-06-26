# Loop ApiDoc — Validation + `validate` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Plan 5 of the loop-apidoc pipeline — the four validation categories (§9.1–9.4), a stable issue-code report (§9.5), an in-memory validator seam reusable by Plan 6, a disk loader, and the `loop-apidoc validate --output <run-dir>` command.

**Architecture:** A new `loop_apidoc/validate/` package mirrors the small-file split of `generate/`. Four pure check modules each return `list[Issue]` from typed inputs (no file I/O). `validator.validate_outputs(plan, result, manifest) -> ValidationReport` aggregates them — this is the seam Plan 6's correction loop calls in-memory. A thin `loader.validate_run_dir(run_dir) -> ValidationReport` deserializes a run directory (catching YAML/JSON/schema failures as structural issues) and delegates to the seam. `report.write_reports` renders `validation/report.json` + `report.md`. The CLI `validate` command wires loader → report → exit code.

**Tech Stack:** Python 3.11+, Pydantic v2, Typer, PyYAML, `openapi-spec-validator>=0.7` (already a declared dependency), `jsonschema>=4.21` (already declared), pytest. Managed with `uv` — every command runs under `uv run`.

## Global Constraints

- Source-grounded only: validation NEVER invents data; it only inspects already-generated artifacts (spec §1, §9.4).
- Python `>=3.11`; every module starts with `from __future__ import annotations`.
- Immutability: check functions never mutate their inputs (`plan`, `result`, `openapi` dict, `manifest`). Copy before any local mutation. (coding-style.md CRITICAL rule — Plan 4's final review caught exactly this class of bug.)
- Issue codes are fixed strings from spec §9.5: `SOURCE_UNVERIFIED`, `REQUIRED_INFO_MISSING`, `SOURCE_CONFLICT`, `OPENAPI_INVALID`, `OUTPUT_MISMATCH`, `UNSUPPORTED_ASSERTION`. Do not add or rename codes.
- Severity policy (locked during brainstorming): blocking `error` = endpoint missing method/path, endpoint with zero responses, authentication absent AND not explicitly marked missing-source, plus any `unverified`/`conflicting` provenance or plan item. Non-blocking `warning` = missing summary, missing examples, missing operational topics. `ValidationReport.ok` is `True` iff there are zero `error`-severity issues. CLI exits 0 when `ok`, else 1 (spec §13).
- Consistency depth (locked during brainstorming): inventory-level only — compare the `(method, path)` set and the security-scheme name set between Markdown and OpenAPI. Per-field/type/enum prose parsing is a Plan 6 carry-forward.
- Run under `uv run python -m pytest ...` / `uv run pytest ...`. Run the FULL suite before each commit; never commit red.
- Commit messages follow `<type>: [validate] <subject>` (project convention, see Plan 4 commits).
- Every test uses hand-built fixtures; no NotebookLM, no network, no real run-dir from a live pipeline.

---

## File Structure

- `loop_apidoc/validate/__init__.py` — package docstring + public exports.
- `loop_apidoc/validate/models.py` — `IssueCode`, `Severity`, `Issue`, `ValidationReport`.
- `loop_apidoc/validate/structure.py` — `check_structure` (§9.1).
- `loop_apidoc/validate/completeness.py` — `check_completeness` (§9.2 + plan-level unverified/conflict surfacing).
- `loop_apidoc/validate/consistency.py` — `check_consistency` (§9.3 inventory level).
- `loop_apidoc/validate/speculation.py` — `check_speculation` (§9.4 field-target provenance).
- `loop_apidoc/validate/validator.py` — `validate_outputs` seam.
- `loop_apidoc/validate/loader.py` — `validate_run_dir` disk layer.
- `loop_apidoc/validate/report.py` — `write_reports`, `render_markdown`.
- `loop_apidoc/cli.py` — add `validate` command (modify).
- `tests/validate/` — one test module per source module + `tests/integration/test_validate_run_dir.py`.

---

## Task 1: Validation models + package skeleton

**Files:**
- Create: `loop_apidoc/validate/__init__.py`
- Create: `loop_apidoc/validate/models.py`
- Create: `tests/validate/__init__.py`
- Test: `tests/validate/test_models.py`

**Interfaces:**
- Produces:
  - `IssueCode(str, Enum)` with members `SOURCE_UNVERIFIED`, `REQUIRED_INFO_MISSING`, `SOURCE_CONFLICT`, `OPENAPI_INVALID`, `OUTPUT_MISMATCH`, `UNSUPPORTED_ASSERTION` (values equal to their names).
  - `Severity(str, Enum)` with `ERROR = "error"`, `WARNING = "warning"`.
  - `Issue(BaseModel)`: `code: IssueCode`, `severity: Severity`, `location: str`, `evidence: str`, `suggested_fix: str`, `auto_fixable: bool = False`.
  - `ValidationReport(BaseModel)`: `issues: list[Issue] = Field(default_factory=list)`; property `ok -> bool` (no error-severity issues); methods `errors() -> list[Issue]`, `warnings() -> list[Issue]`.

- [ ] **Step 1: Write the failing test**

`tests/validate/__init__.py` is empty. `tests/validate/test_models.py`:

```python
from __future__ import annotations

from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)


def _issue(severity: Severity) -> Issue:
    return Issue(
        code=IssueCode.REQUIRED_INFO_MISSING,
        severity=severity,
        location="paths./users.get",
        evidence="no response defined",
        suggested_fix="add a response from source",
    )


def test_issue_code_values_match_spec():
    assert IssueCode.SOURCE_UNVERIFIED.value == "SOURCE_UNVERIFIED"
    assert IssueCode.UNSUPPORTED_ASSERTION.value == "UNSUPPORTED_ASSERTION"
    assert {c.value for c in IssueCode} == {
        "SOURCE_UNVERIFIED",
        "REQUIRED_INFO_MISSING",
        "SOURCE_CONFLICT",
        "OPENAPI_INVALID",
        "OUTPUT_MISMATCH",
        "UNSUPPORTED_ASSERTION",
    }


def test_issue_auto_fixable_defaults_false():
    assert _issue(Severity.WARNING).auto_fixable is False


def test_report_ok_when_no_errors():
    report = ValidationReport(issues=[_issue(Severity.WARNING)])
    assert report.ok is True
    assert report.warnings() == report.issues
    assert report.errors() == []


def test_report_not_ok_with_any_error():
    report = ValidationReport(issues=[_issue(Severity.WARNING), _issue(Severity.ERROR)])
    assert report.ok is False
    assert len(report.errors()) == 1


def test_empty_report_is_ok():
    assert ValidationReport().ok is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/validate/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.validate'`.

- [ ] **Step 3: Write minimal implementation**

`loop_apidoc/validate/models.py`:

```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IssueCode(str, Enum):
    SOURCE_UNVERIFIED = "SOURCE_UNVERIFIED"
    REQUIRED_INFO_MISSING = "REQUIRED_INFO_MISSING"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    OPENAPI_INVALID = "OPENAPI_INVALID"
    OUTPUT_MISMATCH = "OUTPUT_MISMATCH"
    UNSUPPORTED_ASSERTION = "UNSUPPORTED_ASSERTION"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class Issue(BaseModel):
    code: IssueCode
    severity: Severity
    location: str
    evidence: str
    suggested_fix: str
    auto_fixable: bool = False


class ValidationReport(BaseModel):
    issues: list[Issue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity is Severity.ERROR for i in self.issues)

    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]
```

`loop_apidoc/validate/__init__.py` (exports grow in later tasks; start minimal):

```python
"""Validation layer (spec §9)."""

from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)

__all__ = [
    "Issue",
    "IssueCode",
    "Severity",
    "ValidationReport",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/validate/test_models.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/validate/__init__.py loop_apidoc/validate/models.py tests/validate/__init__.py tests/validate/test_models.py
git commit -m "feat: [validate] add issue/report models with severity-based ok"
```

---

## Task 2: Structure validation (§9.1)

**Files:**
- Create: `loop_apidoc/validate/structure.py`
- Test: `tests/validate/test_structure.py`

**Interfaces:**
- Consumes: `Issue`, `IssueCode`, `Severity` (Task 1); `REQUIRED_MARKDOWN_SECTIONS` from `loop_apidoc.generate`.
- Produces: `check_structure(openapi: dict, markdown: str) -> list[Issue]`.
  - Runs `openapi_spec_validator.validate(openapi)`; on `OpenAPIValidationError` emits one `OPENAPI_INVALID` error (`location="openapi"`, `evidence=str(error)[:300]`).
  - Walks the openapi dict for local `$ref` strings (`#/...`); any that does not resolve emits an `OPENAPI_INVALID` error (`location=ref`).
  - For each section in `REQUIRED_MARKDOWN_SECTIONS` not present in `markdown`, emits an `OUTPUT_MISMATCH` error (`location=f"markdown:{section}"`).

- [ ] **Step 1: Write the failing test**

`tests/validate/test_structure.py`:

```python
from __future__ import annotations

from loop_apidoc.generate import REQUIRED_MARKDOWN_SECTIONS
from loop_apidoc.validate.models import IssueCode, Severity
from loop_apidoc.validate.structure import check_structure

_GOOD_OPENAPI = {
    "openapi": "3.1.0",
    "info": {"title": "X", "version": "1.0"},
    "paths": {},
}
_GOOD_MARKDOWN = "\n".join(REQUIRED_MARKDOWN_SECTIONS)


def test_valid_structure_has_no_issues():
    assert check_structure(_GOOD_OPENAPI, _GOOD_MARKDOWN) == []


def test_invalid_openapi_flagged():
    bad = {"openapi": "3.1.0", "info": {"title": "X"}, "paths": {}}  # missing version
    issues = check_structure(bad, _GOOD_MARKDOWN)
    assert any(i.code is IssueCode.OPENAPI_INVALID for i in issues)
    assert all(i.severity is Severity.ERROR for i in issues)


def test_missing_markdown_section_flagged():
    md = _GOOD_MARKDOWN.replace(REQUIRED_MARKDOWN_SECTIONS[0], "")
    issues = check_structure(_GOOD_OPENAPI, md)
    mismatches = [i for i in issues if i.code is IssueCode.OUTPUT_MISMATCH]
    assert len(mismatches) == 1
    assert REQUIRED_MARKDOWN_SECTIONS[0] in mismatches[0].location


def test_unresolvable_ref_flagged():
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "X", "version": "1.0"},
        "paths": {
            "/u": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Ghost"}
                                }
                            },
                        }
                    }
                }
            }
        },
        "components": {"schemas": {}},
    }
    issues = check_structure(doc, _GOOD_MARKDOWN)
    assert any(i.code is IssueCode.OPENAPI_INVALID for i in issues)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/validate/test_structure.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.validate.structure'`.

- [ ] **Step 3: Write minimal implementation**

`loop_apidoc/validate/structure.py`:

```python
from __future__ import annotations

from openapi_spec_validator import validate as validate_openapi
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

from loop_apidoc.generate import REQUIRED_MARKDOWN_SECTIONS
from loop_apidoc.validate.models import Issue, IssueCode, Severity


def _error(code: IssueCode, location: str, evidence: str, fix: str) -> Issue:
    return Issue(
        code=code,
        severity=Severity.ERROR,
        location=location,
        evidence=evidence,
        suggested_fix=fix,
    )


def _iter_refs(node, path: str = ""):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from _iter_refs(value, f"{path}/{key}")
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            yield from _iter_refs(value, f"{path}/{idx}")


def _resolves(ref: str, root: dict) -> bool:
    if not ref.startswith("#/"):
        return False
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return False
    return True


def check_structure(openapi: dict, markdown: str) -> list[Issue]:
    issues: list[Issue] = []
    try:
        validate_openapi(openapi)
    except OpenAPIValidationError as exc:
        issues.append(_error(
            IssueCode.OPENAPI_INVALID, "openapi", str(exc)[:300],
            "修正 OpenAPI 文件使其符合 3.1 schema",
        ))
    for ref in _iter_refs(openapi):
        if not _resolves(ref, openapi):
            issues.append(_error(
                IssueCode.OPENAPI_INVALID, ref, f"$ref 無法解析：{ref}",
                "補上被引用的 components 定義或移除 $ref",
            ))
    for section in REQUIRED_MARKDOWN_SECTIONS:
        if section not in markdown:
            issues.append(_error(
                IssueCode.OUTPUT_MISMATCH, f"markdown:{section}",
                f"Markdown 缺少必要章節：{section}",
                "在 Markdown 補上該章節標題",
            ))
    return issues
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/validate/test_structure.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/validate/structure.py tests/validate/test_structure.py
git commit -m "feat: [validate] structural checks for openapi/refs/markdown sections"
```

---

## Task 3: Completeness validation (§9.2)

**Files:**
- Create: `loop_apidoc/validate/completeness.py`
- Test: `tests/validate/test_completeness.py`

**Interfaces:**
- Consumes: `Issue`, `IssueCode`, `Severity` (Task 1); `NormalizationPlan` and friends from `loop_apidoc.plan.models`.
- Produces: `check_completeness(plan: NormalizationPlan) -> list[Issue]`.
  - Per endpoint (index `i`): missing `method` or `path` → `REQUIRED_INFO_MISSING` **error**; empty `responses` → `REQUIRED_INFO_MISSING` **error**; missing `summary` → **warning**; empty `examples` → **warning**. Endpoint `location` = `f"paths.{path}.{method}"` when both present, else `f"endpoints[{i}]"`.
  - Authentication: if `plan.security_schemes` is empty AND no `plan.missing_items` whose `area` lower-cases to contain `"auth"` or `"security"` → `REQUIRED_INFO_MISSING` **error** at `components.securitySchemes`. If such a missing marker exists, no issue (source explicitly says unprovided).
  - Operational: empty `plan.operational` → `REQUIRED_INFO_MISSING` **warning** at `operational`.
  - Plan-level surfacing: each `plan.unverified_items` → `SOURCE_UNVERIFIED` **error** at `unverified.{area}`; each `plan.source_conflicts` → `SOURCE_CONFLICT` **error** at `conflict.{area}` (spec §6.4 / §9.2: unverified/conflicting sources block completeness).

- [ ] **Step 1: Write the failing test**

`tests/validate/test_completeness.py`:

```python
from __future__ import annotations

from loop_apidoc.plan.models import (
    EndpointEntry,
    MissingItem,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SecuritySchemeEntry,
    SourceConflict,
    UnverifiedItem,
)
from loop_apidoc.validate.completeness import check_completeness
from loop_apidoc.validate.models import IssueCode, Severity


def _endpoint(**kw) -> EndpointEntry:
    base = dict(status=PlanItemStatus.SUPPORTED, method="GET", path="/u",
                summary="s", responses=[{"status": "200"}],
                examples=[{"body": "x"}])
    base.update(kw)
    return EndpointEntry(**base)


def _plan(**kw) -> NormalizationPlan:
    base = dict(
        notebook_url="https://nb/x",
        endpoints=[_endpoint()],
        security_schemes=[SecuritySchemeEntry(status=PlanItemStatus.SUPPORTED, name="A")],
        operational=[OperationalEntry(status=PlanItemStatus.SUPPORTED, topic="rate")],
    )
    base.update(kw)
    return NormalizationPlan(**base)


def _codes(issues, severity):
    return [i.code for i in issues if i.severity is severity]


def test_complete_plan_has_no_errors():
    issues = check_completeness(_plan())
    assert _codes(issues, Severity.ERROR) == []


def test_missing_method_is_error():
    issues = check_completeness(_plan(endpoints=[_endpoint(method=None)]))
    assert IssueCode.REQUIRED_INFO_MISSING in _codes(issues, Severity.ERROR)


def test_no_responses_is_error():
    issues = check_completeness(_plan(endpoints=[_endpoint(responses=[])]))
    assert IssueCode.REQUIRED_INFO_MISSING in _codes(issues, Severity.ERROR)


def test_missing_summary_is_warning_only():
    issues = check_completeness(_plan(endpoints=[_endpoint(summary=None)]))
    assert _codes(issues, Severity.ERROR) == []
    assert IssueCode.REQUIRED_INFO_MISSING in _codes(issues, Severity.WARNING)


def test_no_security_and_no_marker_is_error():
    issues = check_completeness(_plan(security_schemes=[]))
    assert IssueCode.REQUIRED_INFO_MISSING in _codes(issues, Severity.ERROR)


def test_no_security_but_marked_missing_is_ok():
    plan = _plan(security_schemes=[],
                 missing_items=[MissingItem(area="authentication", detail="來源未提供")])
    assert _codes(check_completeness(plan), Severity.ERROR) == []


def test_unverified_item_is_error():
    plan = _plan(unverified_items=[UnverifiedItem(area="sources", detail="無法確認")])
    issues = check_completeness(plan)
    assert IssueCode.SOURCE_UNVERIFIED in _codes(issues, Severity.ERROR)


def test_source_conflict_is_error():
    plan = _plan(source_conflicts=[SourceConflict(area="base_url", detail="兩來源不一致")])
    issues = check_completeness(plan)
    assert IssueCode.SOURCE_CONFLICT in _codes(issues, Severity.ERROR)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/validate/test_completeness.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.validate.completeness'`.

- [ ] **Step 3: Write minimal implementation**

`loop_apidoc/validate/completeness.py`:

```python
from __future__ import annotations

from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.validate.models import Issue, IssueCode, Severity


def _issue(code: IssueCode, severity: Severity, location: str,
           evidence: str, fix: str) -> Issue:
    return Issue(code=code, severity=severity, location=location,
                 evidence=evidence, suggested_fix=fix)


def _endpoint_location(endpoint, index: int) -> str:
    if endpoint.method and endpoint.path:
        return f"paths.{endpoint.path}.{endpoint.method.lower()}"
    return f"endpoints[{index}]"


def _has_auth_marker(plan: NormalizationPlan) -> bool:
    for item in plan.missing_items:
        area = (item.area or "").lower()
        if "auth" in area or "security" in area:
            return True
    return False


def check_completeness(plan: NormalizationPlan) -> list[Issue]:
    issues: list[Issue] = []
    for index, endpoint in enumerate(plan.endpoints):
        location = _endpoint_location(endpoint, index)
        if not endpoint.method or not endpoint.path:
            issues.append(_issue(
                IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR, location,
                "endpoint 缺少 HTTP method 或 path", "由來源補上 method 與 path"))
        if not endpoint.responses:
            issues.append(_issue(
                IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR, location,
                "endpoint 沒有任何 response 定義", "由來源補上 response status 與 schema"))
        if not endpoint.summary:
            issues.append(_issue(
                IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING, location,
                "endpoint 缺少 operation 說明", "由來源補上 operation 說明"))
        if not endpoint.examples:
            issues.append(_issue(
                IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING, location,
                "endpoint 缺少 request/response 範例", "由來源補上範例"))

    if not plan.security_schemes and not _has_auth_marker(plan):
        issues.append(_issue(
            IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR,
            "components.securitySchemes",
            "無 security scheme，且來源未明確標示未提供 authentication",
            "由來源補上 authentication，或記錄為來源未提供"))

    if not plan.operational:
        issues.append(_issue(
            IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING, "operational",
            "缺少 rate limit/timeout/retry 等 operational 資訊", "由來源補上 operational 資訊"))

    for item in plan.unverified_items:
        issues.append(_issue(
            IssueCode.SOURCE_UNVERIFIED, Severity.ERROR, f"unverified.{item.area}",
            item.detail, "確認來源以解除 unverified 狀態"))
    for item in plan.source_conflicts:
        issues.append(_issue(
            IssueCode.SOURCE_CONFLICT, Severity.ERROR, f"conflict.{item.area}",
            item.detail, "揭露並由來源澄清衝突，不可任選其一"))

    return issues
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/validate/test_completeness.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/validate/completeness.py tests/validate/test_completeness.py
git commit -m "feat: [validate] completeness checks with blocking/warning severity policy"
```

---

## Task 4: Consistency validation (§9.3, inventory level)

**Files:**
- Create: `loop_apidoc/validate/consistency.py`
- Test: `tests/validate/test_consistency.py`

**Interfaces:**
- Consumes: `Issue`, `IssueCode`, `Severity` (Task 1).
- Produces: `check_consistency(openapi: dict, markdown: str) -> list[Issue]`.
  - OpenAPI endpoint inventory: `{(method_lower, path)}` from `openapi["paths"]`, keeping only HTTP method keys.
  - Markdown endpoint inventory: parse lines matching `### \`METHOD\` \`path\`` (the exact header `generate/markdown.py` emits), normalizing method to lower-case.
  - Each `(method, path)` in one set but not the other → `OUTPUT_MISMATCH` **error** (`location=f"paths.{path}.{method}"`).
  - Security scheme name inventory: OpenAPI `components.securitySchemes` keys vs Markdown lines matching `- **NAME**（type`. Symmetric-difference names → `OUTPUT_MISMATCH` **error** (`location=f"components.securitySchemes.{name}"`).

- [ ] **Step 1: Write the failing test**

`tests/validate/test_consistency.py`:

```python
from __future__ import annotations

from loop_apidoc.validate.consistency import check_consistency
from loop_apidoc.validate.models import IssueCode

_OPENAPI = {
    "openapi": "3.1.0",
    "info": {"title": "X", "version": "1.0"},
    "paths": {"/users": {"get": {"responses": {"200": {"description": "ok"}}}}},
    "components": {"securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X"}}},
}
_MARKDOWN_MATCH = (
    "## Endpoint\n"
    "### `GET` `/users`\n"
    "## 驗證／授權\n"
    "- **ApiKeyAuth**（type：`apiKey`，位置：`header`，名稱：`X`）\n"
)


def test_matching_inventory_has_no_issues():
    assert check_consistency(_OPENAPI, _MARKDOWN_MATCH) == []


def test_openapi_endpoint_absent_from_markdown_flagged():
    issues = check_consistency(_OPENAPI, "## Endpoint\n## 驗證／授權\n"
                               "- **ApiKeyAuth**（type：`apiKey`）\n")
    assert any(i.code is IssueCode.OUTPUT_MISMATCH and "/users" in i.location
               for i in issues)


def test_markdown_endpoint_absent_from_openapi_flagged():
    md = _MARKDOWN_MATCH + "### `POST` `/ghost`\n"
    issues = check_consistency(_OPENAPI, md)
    assert any(i.code is IssueCode.OUTPUT_MISMATCH and "/ghost" in i.location
               for i in issues)


def test_security_name_mismatch_flagged():
    md = (
        "## Endpoint\n### `GET` `/users`\n"
        "## 驗證／授權\n- **OtherAuth**（type：`apiKey`）\n"
    )
    issues = check_consistency(_OPENAPI, md)
    assert any(i.code is IssueCode.OUTPUT_MISMATCH and "securitySchemes" in i.location
               for i in issues)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/validate/test_consistency.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.validate.consistency'`.

- [ ] **Step 3: Write minimal implementation**

`loop_apidoc/validate/consistency.py`:

```python
from __future__ import annotations

import re

from loop_apidoc.validate.models import Issue, IssueCode, Severity

_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
_ENDPOINT_RE = re.compile(r"^### `([A-Za-z]+)` `([^`]+)`")
_SECURITY_RE = re.compile(r"^- \*\*(.+?)\*\*（type")


def _mismatch(location: str, evidence: str) -> Issue:
    return Issue(
        code=IssueCode.OUTPUT_MISMATCH,
        severity=Severity.ERROR,
        location=location,
        evidence=evidence,
        suggested_fix="重新生成使 Markdown 與 OpenAPI inventory 一致",
    )


def _openapi_endpoints(openapi: dict) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for path, item in (openapi.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in item:
            if method.lower() in _HTTP_METHODS:
                out.add((method.lower(), path))
    return out


def _markdown_endpoints(markdown: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for line in markdown.splitlines():
        match = _ENDPOINT_RE.match(line)
        if match:
            out.add((match.group(1).lower(), match.group(2)))
    return out


def _openapi_security(openapi: dict) -> set[str]:
    schemes = (openapi.get("components") or {}).get("securitySchemes") or {}
    return set(schemes.keys())


def _markdown_security(markdown: str) -> set[str]:
    out: set[str] = set()
    for line in markdown.splitlines():
        match = _SECURITY_RE.match(line)
        if match:
            out.add(match.group(1))
    return out


def check_consistency(openapi: dict, markdown: str) -> list[Issue]:
    issues: list[Issue] = []
    api_eps = _openapi_endpoints(openapi)
    md_eps = _markdown_endpoints(markdown)
    for method, path in sorted(api_eps - md_eps):
        issues.append(_mismatch(
            f"paths.{path}.{method}",
            f"OpenAPI 有 {method.upper()} {path} 但 Markdown 缺少"))
    for method, path in sorted(md_eps - api_eps):
        issues.append(_mismatch(
            f"paths.{path}.{method}",
            f"Markdown 有 {method.upper()} {path} 但 OpenAPI 缺少"))

    api_sec = _openapi_security(openapi)
    md_sec = _markdown_security(markdown)
    for name in sorted(api_sec ^ md_sec):
        issues.append(_mismatch(
            f"components.securitySchemes.{name}",
            f"security scheme {name} 在 Markdown 與 OpenAPI 不一致"))
    return issues
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/validate/test_consistency.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/validate/consistency.py tests/validate/test_consistency.py
git commit -m "feat: [validate] inventory-level markdown/openapi consistency checks"
```

---

## Task 5: No-speculation validation (§9.4)

**Files:**
- Create: `loop_apidoc/validate/speculation.py`
- Test: `tests/validate/test_speculation.py`

**Interfaces:**
- Consumes: `Issue`, `IssueCode`, `Severity` (Task 1); `ProvenanceDocument` from `loop_apidoc.generate.models`; `PlanItemStatus` from `loop_apidoc.plan.models`; `X_LOOP_STATUS`, `MISSING_STATUS` from `loop_apidoc.generate.openapi`.
- Produces: `check_speculation(openapi: dict, provenance: ProvenanceDocument) -> list[Issue]`.
  - Enumerate asserted field targets present in `openapi` using the SAME target strings the provenance generator emits: `info.title`, `info.version`, `servers[i]`, `components.securitySchemes.{name}`, `paths.{path}.{method}`, `components.schemas.{name}`.
  - Skip a target whose openapi node carries `x-loop-status: missing-source` (declared placeholder, not an assertion — handled by completeness/provenance MISSING).
  - For each remaining asserted target, gather provenance statuses for that exact target:
    - none → `UNSUPPORTED_ASSERTION` **error** ("無來源映射").
    - any `CONFLICTING` → `SOURCE_CONFLICT` **error**.
    - else any `SUPPORTED` → ok.
    - else (only `UNVERIFIED`/`MISSING`) → `SOURCE_UNVERIFIED` **error**.

- [ ] **Step 1: Write the failing test**

`tests/validate/test_speculation.py`:

```python
from __future__ import annotations

from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.validate.models import IssueCode
from loop_apidoc.validate.speculation import check_speculation

_OPENAPI = {
    "openapi": "3.1.0",
    "info": {"title": "X", "version": "1.0"},
    "paths": {"/users": {"get": {"responses": {"200": {"description": "ok"}}}}},
}


def _prov(*entries) -> ProvenanceDocument:
    return ProvenanceDocument(notebook_url="https://nb/x", entries=list(entries))


def _e(target, status) -> ProvenanceEntry:
    return ProvenanceEntry(target=target, status=status)


def _supported_prov() -> ProvenanceDocument:
    return _prov(
        _e("info.title", PlanItemStatus.SUPPORTED),
        _e("info.version", PlanItemStatus.SUPPORTED),
        _e("paths./users.get", PlanItemStatus.SUPPORTED),
    )


def test_all_supported_has_no_issues():
    assert check_speculation(_OPENAPI, _supported_prov()) == []


def test_missing_provenance_is_unsupported_assertion():
    prov = _prov(
        _e("info.title", PlanItemStatus.SUPPORTED),
        _e("info.version", PlanItemStatus.SUPPORTED),
    )  # no paths./users.get
    issues = check_speculation(_OPENAPI, prov)
    assert any(i.code is IssueCode.UNSUPPORTED_ASSERTION
               and i.location == "paths./users.get" for i in issues)


def test_conflicting_provenance_flagged():
    prov = _prov(
        _e("info.title", PlanItemStatus.SUPPORTED),
        _e("info.version", PlanItemStatus.SUPPORTED),
        _e("paths./users.get", PlanItemStatus.CONFLICTING),
    )
    issues = check_speculation(_OPENAPI, prov)
    assert any(i.code is IssueCode.SOURCE_CONFLICT for i in issues)


def test_unverified_only_provenance_flagged():
    prov = _prov(
        _e("info.title", PlanItemStatus.SUPPORTED),
        _e("info.version", PlanItemStatus.SUPPORTED),
        _e("paths./users.get", PlanItemStatus.UNVERIFIED),
    )
    issues = check_speculation(_OPENAPI, prov)
    assert any(i.code is IssueCode.SOURCE_UNVERIFIED for i in issues)


def test_missing_source_placeholder_is_skipped():
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "X", "version": "1.0"},
        "paths": {
            "/ping": {"get": {"responses": {
                "default": {"description": "x", "x-loop-status": "missing-source"}}}}
        },
        "components": {"securitySchemes": {
            "scheme0": {"type": "apiKey", "in": "header", "name": "A",
                        "x-loop-status": "missing-source"}}},
    }
    prov = _prov(
        _e("info.title", PlanItemStatus.SUPPORTED),
        _e("info.version", PlanItemStatus.SUPPORTED),
        _e("paths./ping.get", PlanItemStatus.SUPPORTED),
    )  # no provenance for scheme0 — but it is a missing-source placeholder
    issues = check_speculation(doc, prov)
    assert all("securitySchemes" not in i.location for i in issues)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/validate/test_speculation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.validate.speculation'`.

- [ ] **Step 3: Write minimal implementation**

`loop_apidoc/validate/speculation.py`:

```python
from __future__ import annotations

from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.generate.openapi import MISSING_STATUS, X_LOOP_STATUS
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.validate.models import Issue, IssueCode, Severity

_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _is_placeholder(node) -> bool:
    return isinstance(node, dict) and node.get(X_LOOP_STATUS) == MISSING_STATUS


def _asserted_targets(openapi: dict) -> list[tuple[str, object]]:
    """(target, openapi-node) for each field that asserts a fact."""
    targets: list[tuple[str, object]] = []
    info = openapi.get("info") or {}
    targets.append(("info.title", info))
    targets.append(("info.version", info))
    for idx, server in enumerate(openapi.get("servers") or []):
        targets.append((f"servers[{idx}]", server))
    schemes = (openapi.get("components") or {}).get("securitySchemes") or {}
    for name, node in schemes.items():
        targets.append((f"components.securitySchemes.{name}", node))
    for path, item in (openapi.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, node in item.items():
            if method.lower() in _HTTP_METHODS:
                targets.append((f"paths.{path}.{method.lower()}", node))
    schemas = (openapi.get("components") or {}).get("schemas") or {}
    for name, node in schemas.items():
        targets.append((f"components.schemas.{name}", node))
    return targets


def _issue(code: IssueCode, location: str, evidence: str, fix: str) -> Issue:
    return Issue(code=code, severity=Severity.ERROR, location=location,
                 evidence=evidence, suggested_fix=fix)


def check_speculation(openapi: dict, provenance: ProvenanceDocument) -> list[Issue]:
    by_target: dict[str, list[PlanItemStatus]] = {}
    for entry in provenance.entries:
        by_target.setdefault(entry.target, []).append(entry.status)

    issues: list[Issue] = []
    for target, node in _asserted_targets(openapi):
        if _is_placeholder(node):
            continue
        statuses = by_target.get(target, [])
        if not statuses:
            issues.append(_issue(
                IssueCode.UNSUPPORTED_ASSERTION, target,
                "規格欄位無任何 provenance 映射", "為此欄位補上來源引用或移除"))
        elif PlanItemStatus.CONFLICTING in statuses:
            issues.append(_issue(
                IssueCode.SOURCE_CONFLICT, target,
                "規格欄位的來源彼此衝突", "揭露衝突並由來源澄清"))
        elif PlanItemStatus.SUPPORTED in statuses:
            continue
        else:
            issues.append(_issue(
                IssueCode.SOURCE_UNVERIFIED, target,
                "規格欄位僅有 unverified 來源，缺 supported 依據", "確認來源以取得 supported 引用"))
    return issues
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/validate/test_speculation.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/validate/speculation.py tests/validate/test_speculation.py
git commit -m "feat: [validate] no-speculation provenance checks for asserted fields"
```

---

## Task 6: Validator seam (`validate_outputs`)

**Files:**
- Create: `loop_apidoc/validate/validator.py`
- Modify: `loop_apidoc/validate/__init__.py` (add `validate_outputs` export)
- Test: `tests/validate/test_validator.py`

**Interfaces:**
- Consumes: `check_structure`, `check_completeness`, `check_consistency`, `check_speculation` (Tasks 2–5); `ValidationReport` (Task 1); `NormalizationPlan`; `GenerateResult`, `Manifest`.
- Produces: `validate_outputs(plan: NormalizationPlan, result: GenerateResult, manifest: Manifest) -> ValidationReport`.
  - Concatenates the four check lists into one `ValidationReport`.
  - `manifest` is accepted for seam stability and Plan 6's §6 manifest-coverage deepening; not consumed by current checks.

- [ ] **Step 1: Write the failing test**

`tests/validate/test_validator.py`:

```python
from __future__ import annotations

from datetime import datetime

from loop_apidoc.generate import build_result
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SecuritySchemeEntry,
    SourceCitation,
    SystemGroup,
)
from loop_apidoc.validate import validate_outputs

_NOW = datetime(2026, 6, 26, 12, 0, 0)


def _cite() -> SourceCitation:
    return SourceCitation(query_id="06", answer_path="answers/06.txt",
                          manifest_source="api.md", locator="p.1")


def _manifest() -> Manifest:
    return Manifest(
        sources_root="./sources", generated_at=_NOW,
        local_sources=[LocalSource(
            relative_path="api.md", mime_type="text/markdown",
            source_format=SourceFormat.MARKDOWN, size_bytes=10, sha256="abc",
            scanned_at=_NOW, supported=True, status=ProcessingStatus.PENDING)])


def _good_plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="https://nb/x",
        system_groups=[SystemGroup(name="Loop API")],
        overview_note="API。",
        environments=[EnvironmentEntry(
            status=PlanItemStatus.SUPPORTED, name="prod",
            base_url="https://api.example.com", version="2024-01", citations=[_cite()])],
        security_schemes=[SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth", type="apiKey",
            location="header", details="X-API-Key", citations=[_cite()])],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
            summary="List", responses=[{"status": "200", "description": "ok"}],
            examples=[{"body": "{}"}], citations=[_cite()])],
        operational=[OperationalEntry(status=PlanItemStatus.SUPPORTED,
                                      topic="rate", detail="60/min", citations=[_cite()])])


def test_good_outputs_validate_clean():
    plan = _good_plan()
    report = validate_outputs(plan, build_result(plan, _manifest()), _manifest())
    assert report.ok is True, [i.model_dump() for i in report.errors()]


def test_missing_method_makes_report_not_ok():
    plan = _good_plan()
    plan.endpoints[0].method = None
    report = validate_outputs(plan, build_result(plan, _manifest()), _manifest())
    assert report.ok is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/validate/test_validator.py -v`
Expected: FAIL with `ImportError: cannot import name 'validate_outputs'`.

- [ ] **Step 3: Write minimal implementation**

`loop_apidoc/validate/validator.py`:

```python
from __future__ import annotations

from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.validate.completeness import check_completeness
from loop_apidoc.validate.consistency import check_consistency
from loop_apidoc.validate.models import ValidationReport
from loop_apidoc.validate.speculation import check_speculation
from loop_apidoc.validate.structure import check_structure


def validate_outputs(
    plan: NormalizationPlan, result: GenerateResult, manifest: Manifest
) -> ValidationReport:
    """Aggregate the four §9 validation categories. Pure; Plan 6 reuses this seam.

    `manifest` is reserved for Plan 6's §6 manifest-coverage deepening.
    """
    issues = []
    issues += check_structure(result.openapi, result.markdown)
    issues += check_completeness(plan)
    issues += check_consistency(result.openapi, result.markdown)
    issues += check_speculation(result.openapi, result.provenance)
    return ValidationReport(issues=issues)
```

Update `loop_apidoc/validate/__init__.py`:

```python
"""Validation layer (spec §9)."""

from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)
from loop_apidoc.validate.validator import validate_outputs

__all__ = [
    "Issue",
    "IssueCode",
    "Severity",
    "ValidationReport",
    "validate_outputs",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/validate/test_validator.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/validate/validator.py loop_apidoc/validate/__init__.py tests/validate/test_validator.py
git commit -m "feat: [validate] add validate_outputs seam aggregating four checks"
```

---

## Task 7: Disk loader (`validate_run_dir`)

**Files:**
- Create: `loop_apidoc/validate/loader.py`
- Modify: `loop_apidoc/validate/__init__.py` (add `validate_run_dir` export)
- Test: `tests/validate/test_loader.py`

**Interfaces:**
- Consumes: `validate_outputs` (Task 6); `ValidationReport`, `Issue`, `IssueCode`, `Severity` (Task 1); `ProvenanceDocument`, `GenerateResult` (`loop_apidoc.generate.models`); `NormalizationPlan`, `Manifest`.
- Produces: `validate_run_dir(run_dir: Path) -> ValidationReport`.
  - Reads `openapi.yaml`, `api-guide.zh-TW.md`, `provenance.json`, `plan/normalization-plan.json`, `manifest.json` from `run_dir`.
  - YAML unparseable → single `OPENAPI_INVALID` error report.
  - Any required artifact missing or schema-invalid (pydantic `ValidationError`) → single `OUTPUT_MISMATCH` error report (`location` names the offending file).
  - On success, builds `GenerateResult(openapi=..., markdown=..., provenance=...)` and returns `validate_outputs(plan, result, manifest)`.

- [ ] **Step 1: Write the failing test**

`tests/validate/test_loader.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loop_apidoc.generate import generate_outputs
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SecuritySchemeEntry,
    SourceCitation,
    SystemGroup,
)
from loop_apidoc.validate import validate_run_dir
from loop_apidoc.validate.models import IssueCode

_NOW = datetime(2026, 6, 26, 12, 0, 0)


def _cite() -> SourceCitation:
    return SourceCitation(query_id="06", answer_path="answers/06.txt",
                          manifest_source="api.md", locator="p.1")


def _manifest() -> Manifest:
    return Manifest(
        sources_root="./sources", generated_at=_NOW,
        local_sources=[LocalSource(
            relative_path="api.md", mime_type="text/markdown",
            source_format=SourceFormat.MARKDOWN, size_bytes=10, sha256="abc",
            scanned_at=_NOW, supported=True, status=ProcessingStatus.PENDING)])


def _plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="https://nb/x",
        system_groups=[SystemGroup(name="Loop API")],
        overview_note="API。",
        environments=[EnvironmentEntry(
            status=PlanItemStatus.SUPPORTED, name="prod",
            base_url="https://api.example.com", version="2024-01", citations=[_cite()])],
        security_schemes=[SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth", type="apiKey",
            location="header", details="X-API-Key", citations=[_cite()])],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
            summary="List", responses=[{"status": "200", "description": "ok"}],
            examples=[{"body": "{}"}], citations=[_cite()])],
        operational=[OperationalEntry(status=PlanItemStatus.SUPPORTED,
                                      topic="rate", detail="60/min", citations=[_cite()])])


def _write_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    manifest = _manifest()
    generate_outputs(_plan(), manifest, run_dir)
    (run_dir / "plan").mkdir(parents=True, exist_ok=True)
    (run_dir / "plan" / "normalization-plan.json").write_text(
        _plan().model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8")
    return run_dir


def test_good_run_dir_validates_clean(tmp_path):
    report = validate_run_dir(_write_run_dir(tmp_path))
    assert report.ok is True, [i.model_dump() for i in report.errors()]


def test_unparseable_yaml_is_openapi_invalid(tmp_path):
    run_dir = _write_run_dir(tmp_path)
    (run_dir / "openapi.yaml").write_text("a: b:\n  - [unclosed", encoding="utf-8")
    report = validate_run_dir(run_dir)
    assert report.ok is False
    assert any(i.code is IssueCode.OPENAPI_INVALID for i in report.issues)


def test_invalid_provenance_json_is_output_mismatch(tmp_path):
    run_dir = _write_run_dir(tmp_path)
    (run_dir / "provenance.json").write_text('{"bad": true}', encoding="utf-8")
    report = validate_run_dir(run_dir)
    assert report.ok is False
    assert any(i.code is IssueCode.OUTPUT_MISMATCH for i in report.issues)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/validate/test_loader.py -v`
Expected: FAIL with `ImportError: cannot import name 'validate_run_dir'`.

- [ ] **Step 3: Write minimal implementation**

`loop_apidoc/validate/loader.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from loop_apidoc.generate.models import GenerateResult, ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport
from loop_apidoc.validate.validator import validate_outputs


def _single(code: IssueCode, location: str, evidence: str, fix: str) -> ValidationReport:
    return ValidationReport(issues=[Issue(
        code=code, severity=Severity.ERROR, location=location,
        evidence=evidence, suggested_fix=fix)])


def validate_run_dir(run_dir: Path) -> ValidationReport:
    openapi_path = run_dir / "openapi.yaml"
    markdown_path = run_dir / "api-guide.zh-TW.md"
    provenance_path = run_dir / "provenance.json"
    plan_path = run_dir / "plan" / "normalization-plan.json"
    manifest_path = run_dir / "manifest.json"

    for required in (openapi_path, markdown_path, provenance_path, plan_path, manifest_path):
        if not required.exists():
            return _single(IssueCode.OUTPUT_MISMATCH, required.name,
                           f"run directory 缺少 {required.name}", "重新執行生成步驟")

    try:
        openapi = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return _single(IssueCode.OPENAPI_INVALID, "openapi.yaml",
                       f"openapi.yaml 無法解析：{str(exc)[:200]}", "修正 YAML 格式")
    if not isinstance(openapi, dict):
        return _single(IssueCode.OPENAPI_INVALID, "openapi.yaml",
                       "openapi.yaml 不是物件", "重新生成 openapi.yaml")

    try:
        provenance = ProvenanceDocument.model_validate_json(
            provenance_path.read_text(encoding="utf-8"))
        plan = NormalizationPlan.model_validate_json(
            plan_path.read_text(encoding="utf-8"))
        manifest = Manifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        return _single(IssueCode.OUTPUT_MISMATCH, "json-artifact",
                       f"JSON artifact schema 不符：{str(exc)[:200]}", "重新生成該 artifact")

    markdown = markdown_path.read_text(encoding="utf-8")
    result = GenerateResult(openapi=openapi, markdown=markdown, provenance=provenance)
    return validate_outputs(plan, result, manifest)
```

Update `loop_apidoc/validate/__init__.py` to add the export:

```python
"""Validation layer (spec §9)."""

from loop_apidoc.validate.loader import validate_run_dir
from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)
from loop_apidoc.validate.validator import validate_outputs

__all__ = [
    "Issue",
    "IssueCode",
    "Severity",
    "ValidationReport",
    "validate_outputs",
    "validate_run_dir",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/validate/test_loader.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/validate/loader.py loop_apidoc/validate/__init__.py tests/validate/test_loader.py
git commit -m "feat: [validate] run-dir loader deserializing artifacts into the seam"
```

---

## Task 8: Report rendering (`report.json` + `report.md`)

**Files:**
- Create: `loop_apidoc/validate/report.py`
- Modify: `loop_apidoc/validate/__init__.py` (add `write_reports` export)
- Test: `tests/validate/test_report.py`

**Interfaces:**
- Consumes: `ValidationReport`, `Issue`, `Severity` (Task 1).
- Produces:
  - `render_markdown(report: ValidationReport) -> str` — human-readable summary; a header line with overall PASS/FAIL plus error/warning counts, then one bullet per issue grouped error-first showing code, severity, location, evidence, suggested fix.
  - `write_reports(report: ValidationReport, validation_dir: Path) -> None` — `mkdir(parents=True, exist_ok=True)`, write `report.json` (`report.model_dump_json(indent=2)`) and `report.md` (`render_markdown`).

- [ ] **Step 1: Write the failing test**

`tests/validate/test_report.py`:

```python
from __future__ import annotations

from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)
from loop_apidoc.validate.report import render_markdown, write_reports


def _report() -> ValidationReport:
    return ValidationReport(issues=[
        Issue(code=IssueCode.REQUIRED_INFO_MISSING, severity=Severity.ERROR,
              location="paths./u.get", evidence="no response", suggested_fix="add response"),
        Issue(code=IssueCode.REQUIRED_INFO_MISSING, severity=Severity.WARNING,
              location="operational", evidence="no rate limit", suggested_fix="add ops"),
    ])


def test_render_markdown_reports_fail_and_counts():
    md = render_markdown(_report())
    assert "FAIL" in md
    assert "REQUIRED_INFO_MISSING" in md
    assert "paths./u.get" in md
    assert "add response" in md


def test_render_markdown_pass_for_empty():
    assert "PASS" in render_markdown(ValidationReport())


def test_write_reports_emits_both_files(tmp_path):
    out = tmp_path / "validation"
    write_reports(_report(), out)
    loaded = ValidationReport.model_validate_json((out / "report.json").read_text())
    assert loaded == _report()
    assert "FAIL" in (out / "report.md").read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/validate/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.validate.report'`.

- [ ] **Step 3: Write minimal implementation**

`loop_apidoc/validate/report.py`:

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.validate.models import Issue, Severity, ValidationReport


def _bullet(issue: Issue) -> str:
    return (
        f"- **{issue.code.value}** ({issue.severity.value}) @ `{issue.location}`\n"
        f"  - 證據：{issue.evidence}\n"
        f"  - 建議修正：{issue.suggested_fix}\n"
        f"  - 可自動修正：{'是' if issue.auto_fixable else '否'}"
    )


def render_markdown(report: ValidationReport) -> str:
    errors = report.errors()
    warnings = report.warnings()
    status = "PASS" if report.ok else "FAIL"
    lines = [
        "# 驗證報告",
        "",
        f"結果：**{status}**（error：{len(errors)}，warning：{len(warnings)}）",
        "",
    ]
    ordered = errors + warnings
    if not ordered:
        lines.append("_未發現問題。_")
    else:
        lines.extend(_bullet(issue) for issue in ordered)
    return "\n".join(lines).rstrip() + "\n"


def write_reports(report: ValidationReport, validation_dir: Path) -> None:
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8")
    (validation_dir / "report.md").write_text(
        render_markdown(report), encoding="utf-8")
```

Update `loop_apidoc/validate/__init__.py` to add `write_reports` (and keep prior exports):

```python
"""Validation layer (spec §9)."""

from loop_apidoc.validate.loader import validate_run_dir
from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)
from loop_apidoc.validate.report import render_markdown, write_reports
from loop_apidoc.validate.validator import validate_outputs

__all__ = [
    "Issue",
    "IssueCode",
    "Severity",
    "ValidationReport",
    "render_markdown",
    "validate_outputs",
    "validate_run_dir",
    "write_reports",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/validate/test_report.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/validate/report.py loop_apidoc/validate/__init__.py tests/validate/test_report.py
git commit -m "feat: [validate] render report.json and human-readable report.md"
```

---

## Task 9: CLI `validate` command + integration test

**Files:**
- Modify: `loop_apidoc/cli.py` (add `validate` command)
- Create: `tests/integration/test_validate_run_dir.py`

**Interfaces:**
- Consumes: `validate_run_dir`, `write_reports` (Tasks 7–8); `generate_outputs` (`loop_apidoc.generate`).
- Produces: `loop-apidoc validate --output <run-dir>` — runs `validate_run_dir`, writes `<run-dir>/validation/report.{json,md}`, echoes a one-line summary, exits 0 when `report.ok` else 1.

- [ ] **Step 1: Write the failing test**

`tests/integration/test_validate_run_dir.py`:

```python
from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.generate import generate_outputs
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SecuritySchemeEntry,
    SourceCitation,
    SystemGroup,
)

runner = CliRunner()
_NOW = datetime(2026, 6, 26, 12, 0, 0)


def _cite() -> SourceCitation:
    return SourceCitation(query_id="06", answer_path="answers/06.txt",
                          manifest_source="api.md", locator="p.1")


def _manifest() -> Manifest:
    return Manifest(
        sources_root="./sources", generated_at=_NOW,
        local_sources=[LocalSource(
            relative_path="api.md", mime_type="text/markdown",
            source_format=SourceFormat.MARKDOWN, size_bytes=10, sha256="abc",
            scanned_at=_NOW, supported=True, status=ProcessingStatus.PENDING)])


def _good_plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="https://nb/x",
        system_groups=[SystemGroup(name="Loop API")],
        overview_note="API。",
        environments=[EnvironmentEntry(
            status=PlanItemStatus.SUPPORTED, name="prod",
            base_url="https://api.example.com", version="2024-01", citations=[_cite()])],
        security_schemes=[SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth", type="apiKey",
            location="header", details="X-API-Key", citations=[_cite()])],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
            summary="List", responses=[{"status": "200", "description": "ok"}],
            examples=[{"body": "{}"}], citations=[_cite()])],
        operational=[OperationalEntry(status=PlanItemStatus.SUPPORTED,
                                      topic="rate", detail="60/min", citations=[_cite()])])


def _setup_run_dir(tmp_path, plan):
    run_dir = tmp_path / "run"
    manifest = _manifest()
    generate_outputs(plan, manifest, run_dir)
    (run_dir / "plan").mkdir(parents=True, exist_ok=True)
    (run_dir / "plan" / "normalization-plan.json").write_text(
        plan.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8")
    return run_dir


def test_validate_command_passes_and_writes_reports(tmp_path):
    run_dir = _setup_run_dir(tmp_path, _good_plan())
    result = runner.invoke(app, ["validate", "--output", str(run_dir)])
    assert result.exit_code == 0, result.output
    assert (run_dir / "validation" / "report.json").exists()
    assert (run_dir / "validation" / "report.md").exists()


def test_validate_command_fails_on_missing_method(tmp_path):
    plan = _good_plan()
    plan.endpoints[0].method = None
    run_dir = _setup_run_dir(tmp_path, plan)
    result = runner.invoke(app, ["validate", "--output", str(run_dir)])
    assert result.exit_code == 1
    assert (run_dir / "validation" / "report.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_validate_run_dir.py -v`
Expected: FAIL — `validate` is not a registered command (Typer exits non-zero with "No such command").

- [ ] **Step 3: Write minimal implementation**

Add to `loop_apidoc/cli.py` — new imports near the top (with the existing imports):

```python
from loop_apidoc.validate import validate_run_dir, write_reports
```

Add the command (place after the `doctor` command, before `def main`):

```python
@app.command()
def validate(
    output: Path = typer.Option(
        ...,
        "--output",
        help="輸出 run 目錄（含 openapi.yaml / provenance.json / plan 等）",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
) -> None:
    """驗證 run 目錄的輸出（結構／完整性／一致性／禁止推測）。"""
    report = validate_run_dir(output)
    write_reports(report, output / "validation")
    status = "PASS" if report.ok else "FAIL"
    typer.echo(
        f"驗證 {status}：error {len(report.errors())}，warning {len(report.warnings())}；"
        f"報告寫入 {output / 'validation'}"
    )
    raise typer.Exit(code=0 if report.ok else 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_validate_run_dir.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest`
Expected: PASS — all prior tests plus the new validate suite (≈ 145 + 33 new). Confirm zero failures before committing.

- [ ] **Step 6: Commit**

```bash
git add loop_apidoc/cli.py tests/integration/test_validate_run_dir.py
git commit -m "feat: [validate] wire loop-apidoc validate command with exit code"
```

---

## Self-Review

**1. Spec coverage:**
- §9.1 structure → Task 2 (`check_structure`: openapi-spec-validator, `$ref` resolution, markdown sections) + Task 7 (YAML-parseable, JSON-artifact schema validity at the disk boundary). ✓
- §9.2 completeness → Task 3 (per-endpoint method/path/responses/auth + summary/examples/operational severity split; unverified/conflict surfacing). ✓
- §9.3 consistency → Task 4 (inventory-level endpoint + security parity). ✓ (deep field parity = documented Plan 6 carry-forward.)
- §9.4 no-speculation → Task 5 (asserted-target provenance: missing/conflicting/unverified). ✓
- §9.5 issue codes + per-issue severity/location/evidence/suggested-fix/auto-fixable → Task 1 model. ✓
- `validate` command + `validation/report.{json,md}` (§5, §8) → Tasks 8–9. ✓
- Exit code 0/non-zero (§13) → Task 9. ✓
- In-memory seam for Plan 6 (§10 correction loop) → Task 6 `validate_outputs`. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**3. Type consistency:** `check_structure(openapi, markdown)`, `check_completeness(plan)`, `check_consistency(openapi, markdown)`, `check_speculation(openapi, provenance)`, `validate_outputs(plan, result, manifest)`, `validate_run_dir(run_dir)`, `write_reports(report, validation_dir)`, `render_markdown(report)` — signatures referenced identically across Tasks 6–9. `IssueCode`/`Severity` enum members consistent. `ValidationReport.ok`/`.errors()`/`.warnings()` used consistently. ✓

**4. Notes / carry-forward to Plan 6:**
- Deep §9.3 field/type/enum/status-code parity (needs Markdown prose parsing).
- §6 manifest-coverage cross-check using `manifest` (the reserved `validate_outputs` param): match each plan citation's `manifest_source` against `manifest.local_sources`, flag unmatched.
- `Issue.auto_fixable` is wired but always `False` here; Plan 6's correction loop sets the classification (convert/format = auto, source-missing/conflict = not).
