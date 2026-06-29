# Generator `oneOf` / `discriminator` Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the extraction declare a body/schema field as a `oneOf` union of already-named member schemas (with an optional `discriminator`), and have the generator emit native OpenAPI 3.1 `oneOf` + `discriminator` instead of degrading to `{"type": "object"}`.

**Architecture:** A new pure helper `_union_schema(field, name_to_key)` in `openapi.py` resolves a field's `one_of` member names to `$ref`s and assembles the union. `name_to_key` (today only reaching responses) is threaded down through the property/body/schema builders so a leaf field's `one_of` can resolve member `$ref`s. `markdown.py` renders the union members on the field line. No change to `speculation.py`, `provenance.py`, or the plan models — `one_of`/`discriminator` ride along inside the existing `list[dict]` field passthrough.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest, `uv` (no `pip`). Generator is pure functions; the single file-I/O exit is unchanged.

## Global Constraints

- **Source is the only ground truth.** `oneOf` is emitted **only** when the extraction declares `one_of`; `discriminator` **only** when the extraction supplies it. A member name that does not resolve to a named, source-grounded schema is dropped — a dangling `$ref` is never invented (same rule as response `schema_ref`).
- **Key naming is snake_case** in the extraction contract: `one_of`, `property_name` (consistent with existing extraction keys). OpenAPI output uses the spec spelling: `oneOf`, `propertyName`.
- **Additive signatures only.** Threading `name_to_key` adds a trailing parameter (default `None`) to each private builder — never a positional break to existing call sites.
- **No new assertion target.** `oneOf`/`discriminator` live *inside* a body/schema node; do not touch `speculation.py` / `provenance.py` / plan models.
- **Out of scope (do not implement):** `examples.py` changes, `anyOf`/`allOf`, schema-level (whole-`SchemaEntry`) unions. Field-level `one_of` is the only mechanism.
- Python: prefer immutable/pure functions; run `uv run ruff check .` clean before each commit.

---

## File Structure

| File | Responsibility | Change |
| --- | --- | --- |
| `loop_apidoc/generate/openapi.py` | OpenAPI doc generation | Add `_union_schema`; make `_property_schema` union-aware; thread `name_to_key` through `_nest_properties` / `_materialize_node` / `_node_schema` / `_build_request_body` / `_build_object_schema` / `_build_schemas`; update call sites. |
| `loop_apidoc/generate/markdown.py` | zh-TW guide generation | `_field_line` renders `oneOf：A / B / C`（+ `判別子`）for `one_of` fields. |
| `skills/loop-apidoc/SKILL.md` | Extraction contract (§3) | Document optional `one_of` / `discriminator` keys + grounding rule. |
| `tests/generate/test_openapi.py` | Generator unit tests | New tests for `_union_schema` / `_property_schema` and end-to-end `build_openapi` union behavior. |
| `tests/generate/test_markdown.py` | Markdown unit tests | New test for the `one_of` field line. |
| `benchmarks/adyen-payments-multimethod/extraction/**` | Regression fixture | Re-ground `paymentMethod` to use `one_of` + `discriminator`; drop the "no native oneOf" `missing` notes. |
| `benchmarks/adyen-payments-multimethod/expected/**`, `notes.md` | Benchmark expectations | Flip the "忠實限制" narrative to "原生 oneOf/discriminator 正面證明"; status + issue-class map unchanged. |
| `tests/test_benchmarks.py` | Benchmark harness | No code change expected; re-run to confirm adyen stays green. A focused adyen `oneOf` assertion lives in `test_openapi.py`. |

---

## Task 1: `_union_schema` helper + union-aware `_property_schema`

**Files:**
- Modify: `loop_apidoc/generate/openapi.py:194-204` (`_property_schema`)
- Modify: `loop_apidoc/generate/openapi.py` (add `_union_schema` just above `_property_schema`)
- Test: `tests/generate/test_openapi.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `_union_schema(field: dict, name_to_key: dict[str, str]) -> dict | None` — returns `{"oneOf": [...], ...}` or `None`.
  - `_property_schema(field: dict, name_to_key: dict[str, str] | None = None) -> dict` — when the field carries a resolvable `one_of`, returns the union instead of the plain type fragment.

- [ ] **Step 1: Write the failing tests**

Append to `tests/generate/test_openapi.py`. First add the import for the two private helpers at the top of the file (next to the existing `build_openapi` import):

```python
from loop_apidoc.generate.openapi import _property_schema, _union_schema
```

Then append these tests:

```python
def test_union_schema_none_without_one_of():
    assert _union_schema({"name": "x", "type": "object"}, {}) is None
    assert _union_schema({"name": "x", "one_of": []}, {"A": "A"}) is None


def test_union_schema_resolves_members_and_keeps_description():
    field = {
        "name": "paymentMethod",
        "one_of": ["CardDetails", "IdealDetails"],
        "description": "pick one",
    }
    name_to_key = {"CardDetails": "CardDetails", "IdealDetails": "IdealDetails"}
    out = _union_schema(field, name_to_key)
    assert out["oneOf"] == [
        {"$ref": "#/components/schemas/CardDetails"},
        {"$ref": "#/components/schemas/IdealDetails"},
    ]
    assert out["description"] == "pick one"
    assert "discriminator" not in out


def test_union_schema_drops_unresolvable_member_keeps_rest():
    field = {"one_of": ["CardDetails", "Nope"]}
    out = _union_schema(field, {"CardDetails": "CardDetails"})
    assert out["oneOf"] == [{"$ref": "#/components/schemas/CardDetails"}]


def test_union_schema_all_unresolvable_returns_none():
    assert _union_schema({"one_of": ["Nope", "AlsoNope"]}, {"A": "A"}) is None


def test_union_schema_discriminator_with_resolvable_mapping():
    field = {
        "one_of": ["CardDetails", "IdealDetails"],
        "discriminator": {
            "property_name": "type",
            "mapping": {"scheme": "CardDetails", "ideal": "IdealDetails", "x": "Nope"},
        },
    }
    name_to_key = {"CardDetails": "CardDetails", "IdealDetails": "IdealDetails"}
    out = _union_schema(field, name_to_key)
    assert out["discriminator"]["propertyName"] == "type"
    # unresolvable mapping target "x"->"Nope" dropped; resolvable ones kept as $refs
    assert out["discriminator"]["mapping"] == {
        "scheme": "#/components/schemas/CardDetails",
        "ideal": "#/components/schemas/IdealDetails",
    }


def test_union_schema_discriminator_without_property_name_ignored():
    field = {"one_of": ["CardDetails"], "discriminator": {"mapping": {"x": "CardDetails"}}}
    out = _union_schema(field, {"CardDetails": "CardDetails"})
    assert "discriminator" not in out


def test_union_schema_empty_mapping_omitted():
    field = {
        "one_of": ["CardDetails"],
        "discriminator": {"property_name": "type", "mapping": {"x": "Nope"}},
    }
    out = _union_schema(field, {"CardDetails": "CardDetails"})
    assert out["discriminator"] == {"propertyName": "type"}


def test_property_schema_returns_union_when_one_of_resolves():
    field = {"name": "pm", "type": "object", "one_of": ["CardDetails"]}
    out = _property_schema(field, {"CardDetails": "CardDetails"})
    assert out == {"oneOf": [{"$ref": "#/components/schemas/CardDetails"}]}


def test_property_schema_falls_back_to_type_when_no_one_of():
    field = {"name": "pm", "type": "object"}
    assert _property_schema(field, {"CardDetails": "CardDetails"}) == {"type": "object"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/generate/test_openapi.py -k "union_schema or property_schema" -v`
Expected: FAIL — `ImportError: cannot import name '_union_schema'` (and `_property_schema` currently takes one positional arg).

- [ ] **Step 3: Add `_union_schema` and make `_property_schema` union-aware**

In `loop_apidoc/generate/openapi.py`, insert `_union_schema` immediately above `_property_schema` (currently at line 194), then replace `_property_schema`. Replace this exact block:

```python
def _property_schema(field: dict) -> dict:
    """One object property fragment from a source field/param dict.
    Field `description` wins over the raw type hint; `enum` is preserved."""
    prop = _schema_from_type(
        field.get("type") if "type" in field else field.get("schema")
    ) or {}
    if field.get("description"):
        prop["description"] = field["description"]
    if field.get("enum"):
        prop["enum"] = field["enum"]
    return prop
```

with:

```python
def _union_schema(field: dict, name_to_key: dict[str, str]) -> dict | None:
    """A native OpenAPI `oneOf` (+ optional `discriminator`) for a field the source
    documents as a union of already-named member schemas. Returns None unless the
    field carries a truthy `one_of` that resolves to at least one named schema — a
    dangling `$ref` is never invented (same rule as response `schema_ref`)."""
    one_of = field.get("one_of")
    if not one_of:
        return None
    members = [
        {"$ref": f"#/components/schemas/{name_to_key[name]}"}
        for name in one_of
        if name in name_to_key
    ]
    if not members:
        return None
    result: dict = {"oneOf": members}
    if field.get("description"):
        result["description"] = field["description"]
    disc = field.get("discriminator")
    if isinstance(disc, dict) and disc.get("property_name"):
        built: dict = {"propertyName": disc["property_name"]}
        mapping = disc.get("mapping")
        if isinstance(mapping, dict):
            resolved = {
                value: f"#/components/schemas/{name_to_key[target]}"
                for value, target in mapping.items()
                if target in name_to_key
            }
            if resolved:
                built["mapping"] = resolved
        result["discriminator"] = built
    return result


def _property_schema(field: dict, name_to_key: dict[str, str] | None = None) -> dict:
    """One object property fragment from a source field/param dict.
    A resolvable `one_of` becomes a native `oneOf` union; otherwise the
    field `description` wins over the raw type hint and `enum` is preserved."""
    union = _union_schema(field, name_to_key or {})
    if union is not None:
        return union
    prop = _schema_from_type(
        field.get("type") if "type" in field else field.get("schema")
    ) or {}
    if field.get("description"):
        prop["description"] = field["description"]
    if field.get("enum"):
        prop["enum"] = field["enum"]
    return prop
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/generate/test_openapi.py -k "union_schema or property_schema" -v`
Expected: PASS (all 9 new tests).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check loop_apidoc/generate/openapi.py tests/generate/test_openapi.py
git add loop_apidoc/generate/openapi.py tests/generate/test_openapi.py
git commit -m "feat: [generate] _union_schema helper + union-aware _property_schema"
```

---

## Task 2: Thread `name_to_key` through body/schema property builders

**Files:**
- Modify: `loop_apidoc/generate/openapi.py:207-259` (`_nest_properties`, `_materialize_node`, `_node_schema`)
- Modify: `loop_apidoc/generate/openapi.py:262-290` (`_build_request_body`)
- Modify: `loop_apidoc/generate/openapi.py:443-445` (call site in `_build_operation`)
- Modify: `loop_apidoc/generate/openapi.py:515-528` (`_build_object_schema`)
- Modify: `loop_apidoc/generate/openapi.py:531-551` (`_build_schemas`)
- Modify: `loop_apidoc/generate/openapi.py:581` (call site in `build_openapi`)
- Test: `tests/generate/test_openapi.py`

**Interfaces:**
- Consumes: `_union_schema` / `_property_schema(field, name_to_key)` from Task 1.
- Produces (all additive trailing `name_to_key` params, default `None`):
  - `_nest_properties(fields, name_to_key=None) -> tuple[dict, list[str]]`
  - `_materialize_node(node, name_to_key=None) -> tuple[dict, list[str]]`
  - `_node_schema(node, name_to_key=None) -> dict`
  - `_build_request_body(request, body_params, name_to_key=None) -> dict`
  - `_build_object_schema(entry, name_to_key=None) -> dict`
  - `_build_schemas(plan, key_map, name_to_key=None) -> dict`

- [ ] **Step 1: Write the failing end-to-end tests**

Append to `tests/generate/test_openapi.py` (the `EndpointEntry`/`SchemaEntry`/`PlanItemStatus` imports already exist):

```python
def _adyen_members():
    return [
        SchemaEntry(status=PlanItemStatus.SUPPORTED, name="CardDetails",
                    fields=[{"name": "type", "type": "string", "required": True}]),
        SchemaEntry(status=PlanItemStatus.SUPPORTED, name="IdealDetails",
                    fields=[{"name": "type", "type": "string", "required": True}]),
        SchemaEntry(status=PlanItemStatus.SUPPORTED, name="ApplePayDetails",
                    fields=[{"name": "type", "type": "string", "required": True}]),
    ]


def test_body_param_one_of_emits_oneof_and_discriminator():
    plan = _plan(
        schemas=_adyen_members(),
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/payments",
            parameters=[{
                "name": "paymentMethod", "in": "body", "type": "object", "required": True,
                "one_of": ["CardDetails", "IdealDetails", "ApplePayDetails"],
                "discriminator": {
                    "property_name": "type",
                    "mapping": {"scheme": "CardDetails", "ideal": "IdealDetails",
                                "applepay": "ApplePayDetails"},
                },
            }],
            responses=[{"status": "200", "description": "ok"}],
        )],
    )
    schema = build_openapi(plan)["paths"]["/payments"]["post"]["requestBody"][
        "content"]["application/json"]["schema"]
    pm = schema["properties"]["paymentMethod"]
    assert pm["oneOf"] == [
        {"$ref": "#/components/schemas/CardDetails"},
        {"$ref": "#/components/schemas/IdealDetails"},
        {"$ref": "#/components/schemas/ApplePayDetails"},
    ]
    assert pm["discriminator"]["propertyName"] == "type"
    assert pm["discriminator"]["mapping"]["scheme"] == "#/components/schemas/CardDetails"


def test_schema_field_one_of_emits_oneof():
    plan = _plan(
        schemas=_adyen_members() + [SchemaEntry(
            status=PlanItemStatus.SUPPORTED, name="PaymentRequest",
            fields=[{"name": "paymentMethod", "type": "object", "required": True,
                     "one_of": ["CardDetails", "IdealDetails"]}],
        )],
    )
    pr = build_openapi(plan)["components"]["schemas"]["PaymentRequest"]
    assert pr["properties"]["paymentMethod"]["oneOf"] == [
        {"$ref": "#/components/schemas/CardDetails"},
        {"$ref": "#/components/schemas/IdealDetails"},
    ]


def test_one_of_all_unresolvable_falls_back_to_object():
    plan = _plan(schemas=[SchemaEntry(
        status=PlanItemStatus.SUPPORTED, name="PaymentRequest",
        fields=[{"name": "paymentMethod", "type": "object",
                 "one_of": ["Nope", "AlsoNope"]}],
    )])
    pr = build_openapi(plan)["components"]["schemas"]["PaymentRequest"]
    assert pr["properties"]["paymentMethod"] == {"type": "object"}


def test_one_of_leaf_is_terminal_not_expanded_as_nested_object():
    # A union leaf with the same name as a would-be parent must not be expanded
    # into a nested dotted-path object; the union wins.
    plan = _plan(
        schemas=_adyen_members() + [SchemaEntry(
            status=PlanItemStatus.SUPPORTED, name="PaymentRequest",
            fields=[
                {"name": "paymentMethod", "type": "object",
                 "one_of": ["CardDetails"]},
                {"name": "paymentMethod.ignored", "type": "string"},
            ],
        )],
    )
    pm = build_openapi(plan)["components"]["schemas"]["PaymentRequest"][
        "properties"]["paymentMethod"]
    assert "oneOf" in pm
    assert "properties" not in pm
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/generate/test_openapi.py -k "one_of or oneof" -v`
Expected: FAIL — the body/schema fields render as `{"type": "object"}` (no `oneOf`) because `name_to_key` is not threaded into the property path yet.

- [ ] **Step 3: Thread `name_to_key` through the nested builders**

In `loop_apidoc/generate/openapi.py`, edit `_nest_properties` — change the signature and the final return to forward `name_to_key`:

```python
def _nest_properties(
    fields: list[dict], name_to_key: dict[str, str] | None = None
) -> tuple[dict, list[str]]:
```

and its last line `return _materialize_node(tree)` becomes:

```python
    return _materialize_node(tree, name_to_key)
```

Replace `_materialize_node`:

```python
def _materialize_node(
    node: dict, name_to_key: dict[str, str] | None = None
) -> tuple[dict, list[str]]:
    properties: dict = {}
    required: list[str] = []
    for key in node["order"]:
        child = node["children"][key]
        properties[key] = _node_schema(child, name_to_key)
        if child["leaf"] and child["leaf"].get("required"):
            required.append(key)
    return properties, required
```

Replace `_node_schema`:

```python
def _node_schema(node: dict, name_to_key: dict[str, str] | None = None) -> dict:
    leaf = node["leaf"]
    # A union leaf is terminal: its members already describe the shape, so it is
    # never also expanded as a nested dotted-path object.
    if leaf is not None and leaf.get("one_of"):
        return _property_schema(leaf, name_to_key)
    if not node["children"]:
        return _property_schema(leaf, name_to_key) if leaf else {}
    child_props, child_required = _materialize_node(node, name_to_key)
    obj: dict = {"type": "object", "properties": child_props}
    if child_required:
        obj["required"] = child_required
    schema = {"type": "array", "items": obj} if node["array"] else obj
    if leaf and leaf.get("description"):
        schema["description"] = leaf["description"]
    return schema
```

- [ ] **Step 4: Thread `name_to_key` through `_build_request_body` and its call site**

Change `_build_request_body`'s signature (line ~262):

```python
def _build_request_body(
    request: dict | None, body_params: list[dict], name_to_key: dict[str, str] | None = None
) -> dict:
```

and its `_nest_properties` call inside the `if body_params:` branch:

```python
        properties, required = _nest_properties(body_params, name_to_key)
```

In `_build_operation`, update the call site (line ~445):

```python
    if request or body_params:
        op["requestBody"] = _build_request_body(request, body_params, name_to_key)
```

- [ ] **Step 5: Thread `name_to_key` through `_build_object_schema` and `_build_schemas`**

Change `_build_object_schema` (line ~515):

```python
def _build_object_schema(entry, name_to_key: dict[str, str] | None = None) -> dict:
    properties, required = _nest_properties(entry.fields, name_to_key)
```

(leave the rest of the function unchanged).

Change `_build_schemas` (line ~531) signature and the `_build_object_schema` call:

```python
def _build_schemas(
    plan: NormalizationPlan, key_map: dict[int, str],
    name_to_key: dict[str, str] | None = None,
) -> dict:
```

and inside it:

```python
            obj = _build_object_schema(entry, name_to_key)
```

In `build_openapi`, update the `_build_schemas` call site (line ~581) to pass the already-computed `name_to_key`:

```python
    schemas = _build_schemas(plan, key_map, name_to_key)
```

- [ ] **Step 6: Run the new tests and the full generator suite**

Run: `uv run pytest tests/generate/test_openapi.py -v`
Expected: PASS — the 4 new union tests plus all pre-existing tests (no regression; `name_to_key` defaults preserve old behavior).

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check loop_apidoc/generate/openapi.py tests/generate/test_openapi.py
git add loop_apidoc/generate/openapi.py tests/generate/test_openapi.py
git commit -m "feat: [generate] thread name_to_key into body/schema builders for oneOf"
```

---

## Task 3: Markdown union rendering in `_field_line`

**Files:**
- Modify: `loop_apidoc/generate/markdown.py:73-91` (`_field_line`)
- Test: `tests/generate/test_markdown.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (reads `field["one_of"]` / `field["discriminator"]` directly off the dict).
- Produces: `_field_line` renders `oneOf：A / B / C` in place of `型別 \`object\``, plus `判別子 \`type\`` when a discriminator property is present.

- [ ] **Step 1: Write the failing test**

Add the import for `_field_line` at the top of `tests/generate/test_markdown.py` (next to the existing `build_markdown` import):

```python
from loop_apidoc.generate.markdown import _field_line
```

Append:

```python
def test_field_line_renders_one_of_members_and_discriminator():
    field = {
        "name": "paymentMethod", "type": "object", "required": True,
        "one_of": ["CardDetails", "IdealDetails", "ApplePayDetails"],
        "discriminator": {"property_name": "type"},
        "description": "pick one",
    }
    line = _field_line("paymentMethod", field)
    assert "oneOf：CardDetails / IdealDetails / ApplePayDetails" in line
    assert "判別子 `type`" in line
    assert "型別 `object`" not in line
    assert "必填" in line
    assert "— pick one" in line


def test_field_line_without_one_of_still_shows_type():
    line = _field_line("amount", {"name": "amount", "type": "object"})
    assert "型別 `object`" in line
    assert "oneOf" not in line
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/generate/test_markdown.py -k "one_of" -v`
Expected: FAIL — `_field_line` still emits `型別 \`object\`` and no `oneOf：` segment.

- [ ] **Step 3: Implement the union branch in `_field_line`**

In `loop_apidoc/generate/markdown.py`, replace this block (line ~78-83):

```python
    bits: list[str] = []
    if location:
        bits.append(f"位置 `{location}`")
    bits.append(f"型別 `{field.get('type') or '-'}`")
    if field.get("required"):
        bits.append("必填")
```

with:

```python
    bits: list[str] = []
    if location:
        bits.append(f"位置 `{location}`")
    one_of = field.get("one_of")
    if one_of:
        bits.append("oneOf：" + " / ".join(str(m) for m in one_of))
        disc = field.get("discriminator")
        if isinstance(disc, dict) and disc.get("property_name"):
            bits.append(f"判別子 `{disc['property_name']}`")
    else:
        bits.append(f"型別 `{field.get('type') or '-'}`")
    if field.get("required"):
        bits.append("必填")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/generate/test_markdown.py -k "one_of" -v`
Expected: PASS.

- [ ] **Step 5: Run the full markdown suite, lint, commit**

```bash
uv run pytest tests/generate/test_markdown.py -v
uv run ruff check loop_apidoc/generate/markdown.py tests/generate/test_markdown.py
git add loop_apidoc/generate/markdown.py tests/generate/test_markdown.py
git commit -m "feat: [generate] render oneOf union members on the api-guide field line"
```

---

## Task 4: Document the `one_of` / `discriminator` contract in `SKILL.md` §3

**Files:**
- Modify: `skills/loop-apidoc/SKILL.md` (§3, after the `**schema_ref**` paragraph around line 94)

**Interfaces:**
- Consumes: nothing. Documentation only — the SKILL is the extraction contract the agent reads.
- Produces: no code; a new contract paragraph the extraction agent follows.

- [ ] **Step 1: Add the `one_of` / `discriminator` contract paragraph**

In `skills/loop-apidoc/SKILL.md`, immediately after the existing `**`schema_ref`**:` paragraph (the one ending "...never invent a name that isn't in `inventory.schemas`."), insert:

```markdown
**`one_of` / `discriminator`** (optional, for polymorphic fields): an `in:body` parameter or a `schemas[].fields` entry MAY declare a union when the source documents the field as **one of** several named member shapes (e.g. a single `POST /payments` whose `paymentMethod` is one of `CardDetails` / `IdealDetails` / `ApplePayDetails`, selected by a `type` discriminator):

​```json
{"name":"paymentMethod","in":"body","type":"object","required":true,
 "one_of":["CardDetails","IdealDetails","ApplePayDetails"],
 "discriminator":{"property_name":"type",
   "mapping":{"scheme":"CardDetails","ideal":"IdealDetails","applepay":"ApplePayDetails"}}}
​```

- `one_of`: a list of schema **names**, each of which MUST also appear as a named entry in `inventory.schemas` (so every member is independently captured and provenance-backed). A name that isn't in `inventory.schemas` is dropped — never invent one.
- `discriminator` (optional): `property_name` is the **source-stated** discriminating property; `mapping` maps each discriminator value to a member schema **name**. Omit `discriminator` entirely when the source states no explicit discriminator.
- **Grounding rule:** declare `one_of` only when the source documents the field as one of those member shapes; never synthesize a union from REST/payment conventions. Keys are snake_case (`one_of`, `property_name`), consistent with the other extraction keys.
```

(Note: the `​```json` fences above use a zero-width-space marker only so this plan renders — in the actual `SKILL.md` edit, use plain triple-backtick ` ``` ` fences.)

- [ ] **Step 2: Verify the section reads correctly**

Run: `grep -n "one_of\|discriminator\|property_name" skills/loop-apidoc/SKILL.md`
Expected: the new paragraph's keys appear in §3, after `schema_ref`.

- [ ] **Step 3: Commit**

```bash
git add skills/loop-apidoc/SKILL.md
git commit -m "docs: [skill] document optional one_of/discriminator field contract"
```

---

## Task 5: Re-ground the `adyen-payments-multimethod` benchmark + focused assertion

**Files:**
- Modify: `benchmarks/adyen-payments-multimethod/extraction/endpoints/ep0.json`
- Modify: `benchmarks/adyen-payments-multimethod/extraction/inventory.json`
- Modify: `benchmarks/adyen-payments-multimethod/expected/validation.expect.json`
- Modify: `benchmarks/adyen-payments-multimethod/expected/minimum.json` (`_note` only)
- Modify: `benchmarks/adyen-payments-multimethod/notes.md`
- Test: `tests/generate/test_openapi_adyen_oneof.py` (new — focused adyen assertion) + `tests/test_benchmarks.py` (re-run, no edit expected)

**Interfaces:**
- Consumes: the full generator union support from Tasks 1–3.
- Produces: a regression fixture where `paymentMethod` carries `one_of` + `discriminator`; benchmark status stays **PASS** with the same `{"REQUIRED_INFO_MISSING.warning": 3}` issue-class map.

- [ ] **Step 1: Write the focused adyen `oneOf` assertion (failing)**

This test assembles the adyen run end-to-end from the *committed* extraction (the same path the benchmark harness uses — `run_assemble_pipeline` from `loop_apidoc.agentcli.assemble`) and reads the generated `openapi.yaml` to assert native `oneOf`. It will fail until Step 3 re-grounds the fixture. This case requires the operator-provided `sources/` (gitignored), so it skips when absent — exactly like `tests/test_benchmarks.py`. Put it in its own file so the `sources`/`yaml` imports stay out of the pure-generator test module — create `tests/generate/test_openapi_adyen_oneof.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from loop_apidoc.agentcli.assemble import run_assemble_pipeline

_CASE = Path(__file__).resolve().parents[2] / "benchmarks" / "adyen-payments-multimethod"
_FIXED_TS = "20260101T000000Z"


def test_adyen_payments_post_body_has_native_oneof(tmp_path):
    if not (_CASE / "sources").is_dir():
        pytest.skip("adyen sources/ not present (operator-provided, gitignored)")
    result = run_assemble_pipeline(
        sources_root=_CASE / "sources",
        extraction_dir=_CASE / "extraction",
        output_root=tmp_path,
        run_id="bench",
        generated_at=_FIXED_TS,
    )
    doc = yaml.safe_load((Path(result.run_dir) / "openapi.yaml").read_text("utf-8"))
    body = doc["paths"]["/payments"]["post"]["requestBody"]["content"][
        "application/json"]["schema"]
    pm = body["properties"]["paymentMethod"]
    refs = {m["$ref"] for m in pm["oneOf"]}
    assert refs == {
        "#/components/schemas/CardDetails",
        "#/components/schemas/IdealDetails",
        "#/components/schemas/ApplePayDetails",
    }
    assert pm["discriminator"]["propertyName"] == "type"
```

> **Step 2 note — confirm `run_assemble_pipeline`'s signature before running.** Verified against `tests/test_benchmarks.py:67-73`: keyword args `sources_root`, `extraction_dir`, `output_root`, `run_id`, `generated_at`; the result exposes `.run_dir` and writes `openapi.yaml` there. If the signature has since drifted, re-read that harness and mirror it — it is the single source of truth for how a committed benchmark is assembled. If adyen's `sources/` is present locally you'll get a real PASS; if not, the test skips (the harness re-run in Step 6 still exercises the assembly when sources exist).

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/generate/test_openapi_adyen_oneof.py -v`
Expected: FAIL — `paymentMethod` is still `{"type": "object"}` (the committed fixture has no `one_of` yet), so `pm["oneOf"]` raises `KeyError`. (If adyen `sources/` isn't present locally, it SKIPs instead — that's acceptable; the fixture re-grounding is still verified by the harness re-run in Step 6.)

- [ ] **Step 3: Re-ground `extraction/endpoints/ep0.json`**

In `benchmarks/adyen-payments-multimethod/extraction/endpoints/ep0.json`, replace the `paymentMethod` parameter object (the one with the long oneOf-prose description) with:

```json
    {
      "name": "paymentMethod",
      "in": "body",
      "type": "object",
      "required": true,
      "one_of": ["CardDetails", "IdealDetails", "ApplePayDetails"],
      "discriminator": {
        "property_name": "type",
        "mapping": {"scheme": "CardDetails", "ideal": "IdealDetails", "applepay": "ApplePayDetails"}
      },
      "description": "The type and required details of a payment method to use, selected by the `type` discriminator. The full spec lists 40+ members; this benchmark captures three representative ones (CardDetails / IdealDetails / ApplePayDetails)."
    }
```

Then remove the endpoint-level `missing` note about oneOf — change the `"missing"` array (currently a single oneOf-limitation string) to empty:

```json
  "missing": []
```

- [ ] **Step 4: Re-ground `extraction/inventory.json`**

Two edits:

1. The `PaymentRequest.paymentMethod` field (around line 98-102): mirror the same `one_of` + `discriminator`, and soften the description so it no longer frames three members as a *limitation*. Replace that field object with:

```json
        {
          "name": "paymentMethod",
          "type": "object",
          "required": true,
          "one_of": ["CardDetails", "IdealDetails", "ApplePayDetails"],
          "discriminator": {
            "property_name": "type",
            "mapping": {"scheme": "CardDetails", "ideal": "IdealDetails", "applepay": "ApplePayDetails"}
          },
          "description": "The type and required details of a payment method, selected by the `type` discriminator (scheme→CardDetails, ideal→IdealDetails, applepay→ApplePayDetails, ...). The full spec lists 40+ members; three representative ones are captured here as named schemas."
        }
```

2. In the top-level `"missing"` array (around line 513-518), **delete** the first item:

```json
    "paymentMethod is a oneOf union over 40+ payment-method detail objects; the pipeline does not emit native OpenAPI oneOf/discriminator, so it is represented as an object plus three named member schemas (faithful limitation, not speculation).",
```

Keep the remaining two `missing` items (CSE algorithm; webhook/HMAC) verbatim — those are genuine gaps.

- [ ] **Step 5: Re-ground the expectation files and notes**

In `benchmarks/adyen-payments-multimethod/expected/validation.expect.json`, rewrite the first `observations` entry from the "忠實限制" framing to the positive-proof framing (status/`current_issue_classes`/`acceptable_warnings` all unchanged):

```json
    "多產品共用 endpoint 的核心:單一 POST /payments 以 paymentMethod.type discriminator 服務 40+ 付款方式。pipeline 現原生產生 OpenAPI oneOf/discriminator——paymentMethod 以 oneOf 指向三個具名成員 schema(CardDetails/IdealDetails/ApplePayDetails)、discriminator.propertyName=type、mapping 對應 scheme/ideal/applepay。此為原生 oneOf/discriminator 的正面證明(機器可用的多型),非忠實限制。api-guide 段落以 oneOf：A / B / C 呈現多型分流,operationId(post_payments / post_payments_details / post_paymentMethods)穩定。",
```

In `benchmarks/adyen-payments-multimethod/expected/minimum.json`, update only the `_note` to drop the "完整 oneOf 為忠實限制(pipeline 不產生原生 oneOf/discriminator)" clause — replace that trailing sentence with: `三個代表性成員(CardDetails/IdealDetails/ApplePayDetails)以具名 schema 呈現,paymentMethod 原生以 oneOf/discriminator 指向它們。` Leave `must_have`, `integration`, `critical_operations`, `critical_security_schemes` untouched.

In `benchmarks/adyen-payments-multimethod/notes.md`, find the "忠實限制" section and update the oneOf line: state that `oneOf`/`discriminator` is now natively emitted, and that the genuine remaining `missing` are the CSE encryption algorithm and the webhook/HMAC (Notification API, out of this spec). (Read the file first; edit the one oneOf bullet, leave the rest.)

- [ ] **Step 6: Re-run `assemble` for adyen and confirm status unchanged**

Run the benchmark harness for adyen only:

Run: `uv run pytest tests/test_benchmarks.py -k adyen -v`
Expected: PASS — status stays **PASS**, `current_issue_classes` stays `{"REQUIRED_INFO_MISSING.warning": 3}`. The harness's openapi-spec-validator step structurally validates the emitted `oneOf` / `discriminator`.

If the harness reports a changed issue-class map or a structural validation error, **stop and debug** (do not edit the expectation to match a regression): the most likely cause is a member name in `one_of` that doesn't match an `inventory.schemas[].name` exactly, or a `mapping` target typo.

- [ ] **Step 7: Run the focused adyen unit test**

Run: `uv run pytest tests/generate/test_openapi_adyen_oneof.py -v`
Expected: PASS when adyen `sources/` is present (now that the fixture carries `one_of`); SKIP otherwise.

- [ ] **Step 8: Full suite + lint**

```bash
uv run pytest
uv run ruff check .
```

Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add benchmarks/adyen-payments-multimethod tests/generate/test_openapi_adyen_oneof.py
git commit -m "feat: [benchmark] adyen re-grounded to native oneOf/discriminator + focused assertion"
```

---

## Self-Review

**Spec coverage:**
- §1 Extraction contract → Task 4 (SKILL.md §3).
- §2 Plan model no change → respected (Global Constraints; no plan-model task).
- §3 Generator `openapi.py` (`_union_schema` + threading) → Tasks 1 & 2.
- §4 Generator `markdown.py` → Task 3.
- §5 No-speculation/provenance no change → respected (Global Constraints; no such task).
- §6 Re-ground adyen benchmark → Task 5 (ep0.json, inventory.json, expect/minimum/notes, re-run).
- §7 Tests → Tasks 1–3 unit tests; Task 5 focused adyen assertion + harness re-run. Every spec test bullet maps: members resolvable (Task 1/2), discriminator (Task 1/2), one unresolvable (Task 1), all unresolvable fallback (Task 1/2), body vs schema field (Task 2), markdown line (Task 3), adyen focused (Task 5), harness green (Task 5).

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N" — all code blocks are concrete. The adyen focused test uses the real `run_assemble_pipeline` entry point (verified against `tests/test_benchmarks.py:67-73`), not an invented helper.

**Type consistency:** `_union_schema(field, name_to_key)` and `_property_schema(field, name_to_key=None)` signatures are consistent across Tasks 1–2. Threaded `name_to_key=None` trailing-param convention is uniform across `_nest_properties` / `_materialize_node` / `_node_schema` / `_build_request_body` / `_build_object_schema` / `_build_schemas`. Extraction keys are snake_case (`one_of`, `property_name`); OpenAPI output keys are `oneOf` / `propertyName` — used consistently in code, tests, and SKILL.md.
