# Correctness Batch 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining tracked correctness follow-ups: reconcile path templates with declared path parameters, recurse into object-typed parameter schemas in the diff, fill diff-classification test coverage, dedup the diff object-detection predicate, and harden CLI summary access + docs.

**Architecture:** Keep every fix narrow and behavior-preserving outside the reported gaps. Extract one shared object-detection helper in the diff comparator, add path-parameter synthesis to the OpenAPI generator plus an `error`-severity consistency check for orphan declared path params, and add regression tests that lock existing diff classifications.

**Tech Stack:** Python 3.11, Typer, Pydantic v2, pytest, existing `loop_apidoc.generate.openapi`, `loop_apidoc.validate.consistency`, `loop_apidoc.diff.compare`, `loop_apidoc.cli` modules.

## Global Constraints

- The source documents are the ONLY source of truth; anything a source does not state is left `null`/recorded, never inferred. A `{token}` in a path template IS source-stated text, so naming a path parameter after it is grounding, not inference; its type stays `{}` (empty schema) because the source stated none.
- A run FAILs iff it has any `error`-severity issue; the new orphan-path-parameter issue is `error`-severity by design.
- Prefer immutable/pure functions outside the existing I/O modules. `_build_operation`/`_build_paths` already construct operation dicts by local assignment — follow that existing pattern.
- Deterministic output: sort emitted findings/issues by stable keys.
- Python `>=3.11`; deps managed with `uv` (no `pip`).

---

## File Structure

- Modify `loop_apidoc/diff/compare.py`: extract `_looks_like_object`; make `_compare_parameters` recurse into object-typed parameter schemas.
- Modify `tests/diff/test_compare_openapi.py`: unit-test `_looks_like_object`; object-typed parameter property change; Item 7 classification coverage; strengthen one location assertion.
- Modify `loop_apidoc/generate/openapi.py`: synthesize minimal path parameters for template tokens with no declaration.
- Modify `tests/generate/test_openapi.py`: assert synthesized path params + matched-token preservation + multi-token order.
- Modify `loop_apidoc/validate/consistency.py`: add `error`-severity `SOURCE_CONFLICT` check for declared `in: path` params with no matching template token.
- Modify `tests/validate/test_consistency.py`: assert the orphan-path-param conflict + no-false-positive cases.
- Modify `loop_apidoc/cli.py`: defensive `.get(...)` on the diff summary echo.
- Modify `docs/PIPELINE_FOLLOWUPS.md`: mark items 6/7 and M1–M3 resolved; record the preprocess flatten-collision open edge; mark the path-parameter edge resolved.

---

## Task 1: Dedup the diff object-detection predicate (M1)

**Files:**
- Modify: `loop_apidoc/diff/compare.py:82-101,158`
- Test: `tests/diff/test_compare_openapi.py`

**Interfaces:**
- Produces: `_looks_like_object(schema: Any) -> bool` — True iff `schema` is a dict that is explicitly `type: object` OR has `properties` and no `type`. Consumed by Task 2.

- [ ] **Step 1: Write the failing unit test**

Append to `tests/diff/test_compare_openapi.py`:

```python
from loop_apidoc.diff.compare import _looks_like_object


def test_looks_like_object_predicate():
    assert _looks_like_object({"type": "object"}) is True
    assert _looks_like_object({"properties": {"a": {"type": "string"}}}) is True
    assert _looks_like_object({"type": "string", "properties": {"a": {}}}) is False
    assert _looks_like_object({"type": "string"}) is False
    assert _looks_like_object("nope") is False
    assert _looks_like_object({}) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/diff/test_compare_openapi.py::test_looks_like_object_predicate -v`
Expected: FAIL with `ImportError: cannot import name '_looks_like_object'`.

- [ ] **Step 3: Extract the shared helper**

In `loop_apidoc/diff/compare.py`, replace the current `_schema_signature` + `_is_object_schema` block (lines 82-101):

```python
def _schema_signature(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    keys = ("type", "$ref", "enum", "oneOf", "anyOf", "allOf", "format")
    signature = {key: schema.get(key) for key in keys if key in schema}
    if schema.get("type") == "object" or (
        "type" not in schema and isinstance(schema.get("properties"), dict)
    ):
        signature["type"] = "object"
    return signature


def _is_object_schema(schema: Any) -> bool:
    return (
        isinstance(schema, dict)
        and (
            schema.get("type") == "object"
            or ("type" not in schema and isinstance(schema.get("properties"), dict))
        )
    )
```

with:

```python
def _looks_like_object(schema: Any) -> bool:
    return isinstance(schema, dict) and (
        schema.get("type") == "object"
        or ("type" not in schema and isinstance(schema.get("properties"), dict))
    )


def _schema_signature(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    keys = ("type", "$ref", "enum", "oneOf", "anyOf", "allOf", "format")
    signature = {key: schema.get(key) for key in keys if key in schema}
    if _looks_like_object(schema):
        signature["type"] = "object"
    return signature
```

Then update the sole `_is_object_schema` call site (was line 158, inside `_compare_schema`):

```python
        if _looks_like_object(base) != _looks_like_object(head):
            return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/diff/test_compare_openapi.py -v`
Expected: PASS — the new predicate test plus all existing implicit/explicit-object equivalence and shape-flip tests stay green (behavior unchanged).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/diff/compare.py tests/diff/test_compare_openapi.py
git commit -m "Extract shared object-detection predicate in diff comparator" \
  -m "Constraint: the schema-changed emission and the object-flip early-return must use one predicate so they cannot drift." \
  -m "Rejected: leaving two inlined copies | a future edit to one could reopen the false-positive gap batch 1 closed." \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Tested: uv run pytest tests/diff/test_compare_openapi.py -v" \
  -m "Not-tested: no behavior change, existing suite is the regression guard."
```

---

## Task 2: Recurse into object-typed parameter schemas (M3)

**Files:**
- Modify: `loop_apidoc/diff/compare.py:284-297`
- Test: `tests/diff/test_compare_openapi.py`

**Interfaces:**
- Consumes: `_looks_like_object` (Task 1); `_compare_schema(base, head, *, area, location, findings, added_required_is_breaking, removed_property_is_breaking)` (existing).

- [ ] **Step 1: Write the failing test**

Append to `tests/diff/test_compare_openapi.py`:

```python
def test_object_typed_parameter_property_removal_is_reported():
    base = _doc()
    head = _doc()
    obj_param = {
        "name": "filter",
        "in": "query",
        "schema": {
            "type": "object",
            "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        },
    }
    base["paths"]["/payments"]["post"]["parameters"].append(obj_param)
    head_param = {
        "name": "filter",
        "in": "query",
        "schema": {"type": "object", "properties": {"a": {"type": "string"}}},
    }
    head["paths"]["/payments"]["post"]["parameters"].append(head_param)

    findings = _findings(base, head)
    removed = [
        f for f in findings
        if f.summary == "property removed"
        and f.location == "POST /payments parameters.query.filter.b"
    ]
    assert len(removed) == 1
    assert removed[0].impact is DiffImpact.CHANGED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/diff/test_compare_openapi.py::test_object_typed_parameter_property_removal_is_reported -v`
Expected: FAIL — current `_compare_parameters` only diffs the signature, so the property-level `property removed` finding is absent.

- [ ] **Step 3: Recurse when the parameter schema is object-shaped**

In `loop_apidoc/diff/compare.py`, inside `_compare_parameters`, replace the shared-key schema block (was lines 284-297) — the loop over `base_params.keys() & head_params.keys()`:

```python
    for key in sorted(base_params.keys() & head_params.keys()):
        base_schema = base_params[key].get("schema")
        head_schema = head_params[key].get("schema")
        if _looks_like_object(base_schema) and _looks_like_object(head_schema):
            _compare_schema(
                base_schema,
                head_schema,
                area="openapi.parameters",
                location=f"{op_key} parameters.{key}",
                findings=findings,
                added_required_is_breaking=True,
                removed_property_is_breaking=False,
            )
        else:
            before = _schema_signature(base_schema)
            after = _schema_signature(head_schema)
            if before != after:
                findings.append(
                    _finding(
                        DiffImpact.BREAKING,
                        "openapi.parameters",
                        f"{op_key} parameters.{key}",
                        "parameter schema changed",
                        before,
                        after,
                    )
                )
        if base_params[key].get("description") != head_params[key].get("description"):
            findings.append(
                _finding(
                    DiffImpact.CHANGED,
                    "openapi.parameters",
                    f"{op_key} parameters.{key}",
                    "parameter description changed",
                    base_params[key].get("description"),
                    head_params[key].get("description"),
                )
            )
```

(`added_required_is_breaking=True` / `removed_property_is_breaking=False` match how request-body object schemas are classified: adding a required property tightens the contract; removing one is `CHANGED`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/diff/test_compare_openapi.py -v`
Expected: PASS — the new object-parameter test plus existing scalar-parameter tests (added/removed/schema-changed/description) stay green.

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/diff/compare.py tests/diff/test_compare_openapi.py
git commit -m "Diff object-typed parameter schemas by property" \
  -m "Constraint: property-level changes inside an object-typed parameter schema were invisible because only the signature was compared." \
  -m "Rejected: recursing for every parameter | scalar params have no properties and would just re-emit the signature finding." \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: keep scalar parameter signature comparison unchanged." \
  -m "Tested: uv run pytest tests/diff/test_compare_openapi.py -v" \
  -m "Not-tested: deeply nested object parameters beyond one property level (covered transitively by _compare_schema recursion)."
```

---

## Task 3: Reconcile path templates with declared path parameters (Item: Open edge)

**Files:**
- Modify: `loop_apidoc/generate/openapi.py:514-534` (`_build_paths`) + new module-level helper
- Modify: `loop_apidoc/validate/consistency.py`
- Test: `tests/generate/test_openapi.py`, `tests/validate/test_consistency.py`

**Interfaces:**
- Produces (generator): path templates with a `{token}` and no declared `in: path` parameter gain a synthesized `{"name": token, "in": "path", "required": True, "schema": {}}` appended after declared parameters, in template-token order.
- Produces (validator): `check_consistency(openapi, markdown)` additionally emits an `error`-severity `Issue(code=SOURCE_CONFLICT)` for each declared `in: path` parameter whose name is absent from its path template.

### Part A — Generator synthesis

- [ ] **Step 1: Write the failing generator tests**

Append to `tests/generate/test_openapi.py`:

```python
def test_path_token_without_declaration_is_synthesized():
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users/{id}",
            responses=[{"status": "200", "description": "ok"}],
        )
    ])
    op = build_openapi(plan)["paths"]["/users/{id}"]["get"]
    path_params = [p for p in op["parameters"] if p["in"] == "path"]
    assert path_params == [
        {"name": "id", "in": "path", "required": True, "schema": {}}
    ]


def test_declared_path_param_is_not_duplicated_by_synthesis():
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users/{id}",
            parameters=[{"name": "id", "in": "path", "type": "string"}],
            responses=[{"status": "200", "description": "ok"}],
        )
    ])
    op = build_openapi(plan)["paths"]["/users/{id}"]["get"]
    path_params = [p for p in op["parameters"] if p["in"] == "path"]
    assert len(path_params) == 1
    assert path_params[0]["name"] == "id"
    assert path_params[0]["schema"] == {"type": "string"}


def test_multiple_path_tokens_synthesized_in_template_order():
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/a/{x}/b/{y}",
            responses=[{"status": "200", "description": "ok"}],
        )
    ])
    op = build_openapi(plan)["paths"]["/a/{x}/b/{y}"]["get"]
    names = [p["name"] for p in op["parameters"] if p["in"] == "path"]
    assert names == ["x", "y"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/generate/test_openapi.py -k "path_token or path_param or path_tokens" -v`
Expected: FAIL — synthesized params are absent (`KeyError`/empty `path_params`).

- [ ] **Step 3: Add token parsing + synthesis to the generator**

In `loop_apidoc/generate/openapi.py` (`re` is already imported at the top), add a module-level helper near `_build_paths`:

```python
# Path template variables are the names inside single `{...}` segments; OpenAPI
# requires every such token to have a matching `in: path` parameter. The token
# name is source-stated (it is literally in the path string), so synthesizing a
# minimal parameter for it is grounding, not inference.
def _path_template_tokens(path: str) -> list[str]:
    seen: list[str] = []
    for token in re.findall(r"\{([^{}/]+)\}", path):
        if token not in seen:
            seen.append(token)
    return seen
```

Then in `_build_paths`, replace the build/store loop (was lines 530-533):

```python
    for (path, method), endpoints in grouped.items():
        op = _build_operation(endpoints, name_to_key, scheme_keys)
        declared_path = {
            param["name"]
            for param in op.get("parameters", [])
            if isinstance(param, dict) and param.get("in") == "path"
        }
        synthesized = [
            {"name": token, "in": "path", "required": True, "schema": {}}
            for token in _path_template_tokens(path)
            if token not in declared_path
        ]
        if synthesized:
            op["parameters"] = op.get("parameters", []) + synthesized
        paths.setdefault(path, {})[method] = op
    return paths
```

- [ ] **Step 4: Run generator tests to verify they pass**

Run: `uv run pytest tests/generate/test_openapi.py -v`
Expected: PASS — the three new tests plus all existing generator tests (including the existing `/users/{id}` declared-param test) stay green.

### Part B — Consistency check for orphan declared path params

- [ ] **Step 5: Write the failing consistency tests**

Append to `tests/validate/test_consistency.py`:

```python
from loop_apidoc.validate.models import Severity


def test_declared_path_param_absent_from_template_is_conflict():
    openapi = {
        "openapi": "3.1.0",
        "info": {"title": "X", "version": "1.0"},
        "paths": {
            "/users": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {}}
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    markdown = "## Endpoint\n### `GET` `/users`\n## 驗證／授權\n"
    conflicts = [
        i for i in check_consistency(openapi, markdown)
        if i.code is IssueCode.SOURCE_CONFLICT
    ]
    assert len(conflicts) == 1
    assert conflicts[0].severity is Severity.ERROR
    assert "id" in conflicts[0].evidence
    assert "/users" in conflicts[0].evidence


def test_path_param_matching_template_is_not_a_conflict():
    openapi = {
        "openapi": "3.1.0",
        "info": {"title": "X", "version": "1.0"},
        "paths": {
            "/users/{id}": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {}}
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    markdown = "## Endpoint\n### `GET` `/users/{id}`\n## 驗證／授權\n"
    assert not [
        i for i in check_consistency(openapi, markdown)
        if i.code is IssueCode.SOURCE_CONFLICT
    ]
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/validate/test_consistency.py -k "path_param" -v`
Expected: FAIL — no `SOURCE_CONFLICT` issue is produced yet.

- [ ] **Step 7: Add the orphan-path-param check**

In `loop_apidoc/validate/consistency.py`, add the import for `Severity` (update the existing models import line):

```python
from loop_apidoc.validate.models import Issue, IssueCode, Severity
```

Add a helper above `check_consistency`:

```python
def _path_parameter_conflicts(openapi: dict) -> list[Issue]:
    issues: list[Issue] = []
    for path, item in sorted((openapi.get("paths") or {}).items()):
        if not isinstance(item, dict):
            continue
        tokens = set(re.findall(r"\{([^{}/]+)\}", path))
        for method, operation in sorted(item.items()):
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            params = operation.get("parameters")
            if not isinstance(params, list):
                continue
            orphans = sorted(
                str(param.get("name"))
                for param in params
                if isinstance(param, dict)
                and param.get("in") == "path"
                and param.get("name")
                and str(param.get("name")) not in tokens
            )
            for name in orphans:
                issues.append(Issue(
                    code=IssueCode.SOURCE_CONFLICT,
                    severity=Severity.ERROR,
                    location=f"paths.{path}.{method.lower()}.parameters.{name}",
                    evidence=f"宣告的 path 參數 '{name}' 不在路徑模板 '{path}' 中",
                    suggested_fix="修正來源:改用正確的參數位置,或在路徑模板補上對應的 {token}",
                ))
    return issues
```

Then, in `check_consistency`, before the final `return issues`:

```python
    issues.extend(_path_parameter_conflicts(openapi))
    return issues
```

- [ ] **Step 8: Run consistency + full targeted tests to verify they pass**

Run: `uv run pytest tests/validate/test_consistency.py tests/generate/test_openapi.py -v`
Expected: PASS — both new consistency tests plus existing consistency tests stay green.

- [ ] **Step 9: Commit**

```bash
git add loop_apidoc/generate/openapi.py loop_apidoc/validate/consistency.py \
  tests/generate/test_openapi.py tests/validate/test_consistency.py
git commit -m "Reconcile path templates with declared path parameters" \
  -m "Constraint: a {token} in a path template is source-stated, so a missing path parameter is synthesized (empty schema); a declared in:path param with no token is a genuine source conflict." \
  -m "Rejected: dropping orphan declared path params silently | that is the exact loss this batch closes." \
  -m "Rejected: editing the path template to add a missing token | that would invent path structure the source never stated." \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: synthesize only from template tokens; surface orphan declared params as error-severity SOURCE_CONFLICT." \
  -m "Tested: uv run pytest tests/generate/test_openapi.py tests/validate/test_consistency.py -v" \
  -m "Not-tested: nested/matrix path templates; only simple {name} segments are parsed."
```

---

## Task 4: Fill diff-classification coverage (Item 7)

**Files:**
- Modify: `tests/diff/test_compare_openapi.py`, `tests/diff/test_compare_supporting_artifacts.py`

These lock existing classifications (verified present in `compare.py`). If any test FAILS, it has exposed a real bug — fix it in `compare.py` under TDD before committing; otherwise they are pure regression insurance.

- [ ] **Step 1: Write the coverage tests**

Append to `tests/diff/test_compare_openapi.py`:

```python
def test_info_title_change_is_changed():
    base = _doc()
    head = _doc()
    head["info"]["title"] = "Renamed API"
    findings = _findings(base, head)
    hits = [f for f in findings if f.location == "openapi.info.title"]
    assert len(hits) == 1
    assert hits[0].impact is DiffImpact.CHANGED


def test_property_no_longer_required_is_changed():
    base = _doc()
    head = _doc()
    schema = head["paths"]["/payments"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    schema["required"] = []
    findings = _findings(base, head)
    hits = [f for f in findings if f.summary == "property no longer required"]
    assert len(hits) == 1
    assert hits[0].impact is DiffImpact.CHANGED


def test_removed_component_schema_is_changed():
    base = _doc()
    base.setdefault("components", {}).setdefault("schemas", {})["Money"] = {
        "type": "object"
    }
    head = _doc()
    findings = _findings(base, head)
    hits = [
        f for f in findings
        if f.location == "components.schemas.Money" and f.summary == "schema removed"
    ]
    assert len(hits) == 1
    assert hits[0].impact is DiffImpact.CHANGED
```

- [ ] **Step 2: Strengthen the response-schema-type assertion**

In `tests/diff/test_compare_openapi.py`, find `test_response_schema_type_change_is_breaking` and change its location assertion from substring membership to exact equality. For example, replace a line of the form:

```python
    assert any("POST /payments responses.200.application/json" in f.location and ... for f in findings)
```

with an explicit lookup and exact match:

```python
    hits = [
        f for f in findings
        if f.location == "POST /payments responses.200.application/json"
        and f.summary == "schema changed"
    ]
    assert len(hits) == 1
    assert hits[0].impact is DiffImpact.BREAKING
```

(Adjust the existing test body to this exact-equality shape; keep whatever base/head mutation it already performs.)

- [ ] **Step 3: Add callbacks + validation coverage in the supporting-artifacts test file**

Append to `tests/diff/test_compare_supporting_artifacts.py` — one test asserting a callback core-field change (`verification` or `expected_response`) classifies as `DiffImpact.BREAKING`, and one asserting a removed validation issue classifies as `DiffImpact.SOURCE_ONLY`. Use the file's existing `_artifacts(...)` / `build_diff_report(...)` helpers and the existing integration-contract and `ValidationReport` construction patterns already imported there:

```python
def test_callback_core_field_change_is_breaking():
    # Build base/head artifacts whose integration callbacks differ only in a core
    # field (verification or expected_response) using this file's _artifacts helper,
    # then assert exactly one finding with area "openapi.callbacks"-style section and
    # impact DiffImpact.BREAKING. Follow the existing crypto/field_conditions tests
    # in this file as the template for constructing the integration contract.
    ...


def test_removed_validation_issue_is_source_only():
    # Build base with one extra ValidationReport issue that head lacks; assert the
    # resulting finding has area "validation" and impact DiffImpact.SOURCE_ONLY.
    ...
```

If this file has no existing callback/integration or validation-issue test to copy the construction from, instead add both tests to whichever `tests/diff/` file already constructs `RunArtifacts` with a populated integration contract and `ValidationReport`; grep first: `rg -l "expected_response|ValidationReport\(" tests/diff`.

- [ ] **Step 4: Run the diff suite**

Run: `uv run pytest tests/diff/ -v`
Expected: PASS. If a coverage test FAILS, it exposed a real classification bug — fix `compare.py` minimally, re-run, and note the fix in the commit body.

- [ ] **Step 5: Commit**

```bash
git add tests/diff/test_compare_openapi.py tests/diff/test_compare_supporting_artifacts.py
git commit -m "Lock diff classification coverage gaps" \
  -m "Constraint: info.title/property-no-longer-required/removed-schema are CHANGED; callback core-field is BREAKING; removed validation issue is SOURCE_ONLY." \
  -m "Rejected: substring location assertions | they let a wrong-location finding pass; exact equality is required." \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Tested: uv run pytest tests/diff/ -v" \
  -m "Not-tested: none beyond the added cases; these are regression insurance."
```

---

## Task 5: Harden CLI summary access and update docs (Item 6 + M2)

**Files:**
- Modify: `loop_apidoc/cli.py:132-139`
- Modify: `docs/PIPELINE_FOLLOWUPS.md`

- [ ] **Step 1: Make the diff summary echo defensive**

In `loop_apidoc/cli.py`, replace the diff summary echo (lines 132-139):

```python
    typer.echo(
        "diff COMPLETE: "
        f"breaking {report.summary['breaking']}，"
        f"additive {report.summary['additive']}，"
        f"changed {report.summary['changed']}，"
        f"source_only {report.summary['source_only']}；"
        f"報告寫入 {output_dir / 'report.json'}"
    )
```

with:

```python
    typer.echo(
        "diff COMPLETE: "
        f"breaking {report.summary.get('breaking', 0)}，"
        f"additive {report.summary.get('additive', 0)}，"
        f"changed {report.summary.get('changed', 0)}，"
        f"source_only {report.summary.get('source_only', 0)}；"
        f"報告寫入 {output_dir / 'report.json'}"
    )
```

- [ ] **Step 2: Verify the diff CLI test still passes**

Run: `uv run pytest -k diff -v`
Expected: PASS — the summary output is unchanged for the normal case where all keys are present.

- [ ] **Step 3: Update `docs/PIPELINE_FOLLOWUPS.md`**

In section 8's `### Recommended Work` list, update items 6 and 7 from "Open for correctness batch 2" to resolved:

```markdown
6. **Resolved (2026-07-02 correctness batch 2): CLI summary key access.** `cli.py`
   diff summary now uses `report.summary.get(k, 0)` defensive lookups.
7. **Resolved (2026-07-02 correctness batch 2): Coverage gaps.** Added diff
   classification tests (`info.title` CHANGED; property-no-longer-required CHANGED;
   removed-component-schema CHANGED; callback core-field → BREAKING;
   validation-issue-removed → SOURCE_ONLY) and strengthened
   `test_response_schema_type_change_is_breaking` to exact-equality location.
```

In the `### Later Correctness Ledger`, update the path-parameter edge and add the flatten-collision edge:

```markdown
- **Resolved (2026-07-02 correctness batch 2): path parameters absent from the URL
  template.** Template tokens without a declared parameter are synthesized (empty
  schema); declared `in: path` params with no matching token surface as an
  `error`-severity `SOURCE_CONFLICT`.
- **Resolved (2026-07-02 correctness batch 2): diff comparator review minors.**
  M1 (object-detection predicate deduped into `_looks_like_object`); M3
  (`_compare_parameters` recurses into object-typed parameter schemas).
- **Open edge:** preprocess flattens `rglob` output into one directory, so sources
  with the same basename in different subdirectories (or a `foo.pdf` and a sibling
  `foo.md`) collide on write and the category counts can overstate files on disk;
  keep this for a later batch with focused fixtures.
```

- [ ] **Step 4: Run full verification**

Run:

```bash
uv run pytest
uv run ruff check .
```

Expected: both PASS. Fix any ruff issues in touched files and re-run `uv run ruff check .`.

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/cli.py docs/PIPELINE_FOLLOWUPS.md
git commit -m "Harden diff summary access and close batch 2 follow-ups" \
  -m "Constraint: summary keys are currently always present, but defensive access matches diff/report.py and avoids a KeyError if a future impact key is renamed." \
  -m "Rejected: leaving literal key access | inconsistent with report.py's .get usage." \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: keep the preprocess flatten-collision edge visible until a dedicated fixture and fix land." \
  -m "Tested: uv run pytest; uv run ruff check ." \
  -m "Not-tested: rendered HTML docs because only markdown tracking files changed."
```

---

## Final Verification Checklist

- [ ] `uv run pytest tests/diff/test_compare_openapi.py -v` passes.
- [ ] `uv run pytest tests/generate/test_openapi.py -v` passes.
- [ ] `uv run pytest tests/validate/test_consistency.py -v` passes.
- [ ] `uv run pytest tests/diff/ -v` passes.
- [ ] `uv run pytest` passes.
- [ ] `uv run ruff check .` passes.
- [ ] `git status --short` shows only intentional changes or a clean tree after commits.

## Self-Review

- Spec coverage: Task 1 = M1 (shared `_looks_like_object`). Task 2 = M3 (object-parameter recursion, consumes Task 1). Task 3 = path-parameter reconciliation (generator synthesis + `error`-severity `SOURCE_CONFLICT` consistency check). Task 4 = Item 7 classification coverage + exact-equality assertion. Task 5 = Item 6 (`.get`) + M2 docs ledger. All spec sections mapped.
- Placeholder scan: Task 4 Step 3's two tests describe construction via the file's existing helpers rather than full code, because the exact `_artifacts`/integration-contract constructor shape lives in the test file and must be copied from its neighbors; a `rg` fallback is given. Every other step contains complete code.
- Type consistency: `_looks_like_object` defined in Task 1 and consumed in Tasks 2 and 3 with the same signature. `_path_template_tokens`, synthesized param shape `{"name","in","required","schema"}`, and `IssueCode.SOURCE_CONFLICT` / `Severity.ERROR` match between generator, validator, and tests. `build_openapi`, `check_consistency`, `_findings`, `_doc` match existing module/test signatures.
- Ordering: Task 1 precedes Tasks 2 and 3 (both consume `_looks_like_object`).
