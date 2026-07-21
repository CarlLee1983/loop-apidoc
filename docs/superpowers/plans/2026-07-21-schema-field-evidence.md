# Schema Field Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve `schemas[].fields[].source` as verified field-level evidence and emit fail-closed provenance for each generated OpenAPI property.

**Architecture:** The agent-input guard accepts the narrowly scoped `source` key and the source guard treats it as inventory-file evidence. The normalization plan converts each source-bearing raw field into a typed evidence record. Provenance maps those records to the property locations generated from the same dotted-name convention; speculation validation uses field provenance when available and parent-schema provenance otherwise.

**Tech Stack:** Python 3.11+, Pydantic v2, Typer CLI, pytest, Ruff, existing plan/generate/validate pipeline.

## Global Constraints

- Source documents remain the only source of truth; never infer citations or fields.
- A field source is optional for backwards compatibility; its absence falls back only to the parent schema's source-grounded provenance.
- A field citation that cannot be resolved against a multi-source manifest must remain fail-closed as `SOURCE_UNVERIFIED`.
- Keep I/O boundaries unchanged: `agentcli`, `plan`, `generate`, and `validate` additions stay pure; only existing writer exits persist artifacts.
- Preserve the existing OpenAPI dotted-field nesting semantics and do not add source annotations to generated OpenAPI.
- Generated product output remains zh-TW; teaching/reference documentation is English-primary with zh-TW support where the existing document establishes it.
- Do not add `--include` or `--source-file`; exact manifest selection is `manifest --sources <file>`.

---

## File Structure

- `loop_apidoc/agentcli/input_schema.py` — accepts the typed optional field citation without relaxing all strict field validation.
- `loop_apidoc/agentcli/source_guard.py` — includes field citations in inventory scope checks.
- `loop_apidoc/plan/models.py` — owns the typed `SchemaFieldEvidence` intermediate record.
- `loop_apidoc/plan/builder.py` — creates evidence and unverified findings while building stage-07 schemas.
- `loop_apidoc/generate/provenance.py` — emits exact field/property provenance targets.
- `loop_apidoc/validate/speculation.py` — enumerates nested schema properties and selects exact field provenance before schema fallback.
- `tests/agentcli/test_input_schema.py` and `tests/agentcli/test_source_guard.py` — exercise acceptance and input-boundary source scope behavior.
- `tests/plan/test_builder.py` — verifies plan-level evidence normalization and unresolved claim recording.
- `tests/generate/test_provenance.py` — verifies direct, dotted, and array property provenance targets.
- `tests/validate/test_speculation.py` — verifies field evidence overrides schema provenance and parent fallback remains valid.
- `skills/loop-apidoc/reference/extraction-schemas.md` — documents the field-level citation contract for extraction agents.

## Task 1: Accept and guard field-level sources

**Files:**
- Modify: `loop_apidoc/agentcli/input_schema.py:60-67`
- Modify: `loop_apidoc/agentcli/source_guard.py:145-154`
- Modify: `tests/agentcli/test_input_schema.py:163-182`
- Modify: `tests/agentcli/test_source_guard.py:123-151`

**Interfaces:**
- Consumes: raw `inventory.json` schema field dictionaries.
- Produces: `FieldEntry.source: str | None` and inventory-scope citations labelled `schemas[<schema>].fields[<field>].source`.

- [ ] **Step 1: Write the failing input-schema test**

Add this test to `tests/agentcli/test_input_schema.py`:

```python
def test_schema_field_source_is_accepted(tmp_path):
    inv = json.loads(json.dumps(_INVENTORY))
    inv["schemas"][0]["fields"][0]["source"] = "spec.md p.12"
    extraction = tmp_path / "x"
    _write(extraction, inventory=inv)

    loaded, _, _ = load_extraction_inputs(extraction)

    assert loaded["schemas"][0]["fields"][0]["source"] == "spec.md p.12"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/agentcli/test_input_schema.py::test_schema_field_source_is_accepted -v`

Expected: FAIL with `Extra inputs are not permitted` at the field `source` path.

- [ ] **Step 3: Implement the narrow input-model change**

Add only this field to `FieldEntry` in `loop_apidoc/agentcli/input_schema.py`:

```python
class FieldEntry(_StrictEntry):
    name: str
    type: str | None = None
    required: bool | None = None
    description: str | None = None
    one_of: list[str] | None = None
    discriminator: dict[str, Any] | None = None
    source: str | None = None
```

Do not change `_StrictEntry` or the tolerated-key list; other accidental localized or unknown keys must still fail.

- [ ] **Step 4: Run the input-schema test to verify it passes**

Run: `uv run pytest tests/agentcli/test_input_schema.py::test_schema_field_source_is_accepted -v`

Expected: PASS.

- [ ] **Step 5: Write the failing source-guard test**

Add this test to `tests/agentcli/test_source_guard.py`:

```python
def test_schema_field_sources_belong_to_inventory_source_scope():
    manifest = _manifest("a.pdf", "b.pdf")
    inventory = {"schemas": [{"source": "schema missing", "fields": [
        {"name": "amount", "source": "a.pdf p.9"},
    ]}]}

    assert source_violations(inventory, [], None, manifest) == []
```

- [ ] **Step 6: Run the source-guard test to verify it fails**

Run: `uv run pytest tests/agentcli/test_source_guard.py::test_schema_field_sources_belong_to_inventory_source_scope -v`

Expected: FAIL because the guard currently only collects `schemas[0].source`.

- [ ] **Step 7: Implement field citation collection**

In `source_violations`, construct `inventory_scope` with existing section-level entries plus this nested collection:

```python
field_scope = [
    ("inventory.json", f"schemas[{schema_idx}].fields[{field_idx}].source", field["source"])
    for schema_idx, schema in enumerate(_entries(inventory, "schemas"))
    for field_idx, field in enumerate(schema.get("fields") or [])
    if isinstance(field, dict) and _cited(field.get("source"))
]
inventory_scope = [*inventory_scope, *field_scope]
```

Keep all citations in the single `inventory.json` scope: one matching source proves the file follows the format contract, while individual unresolved claims remain validation work.

- [ ] **Step 8: Run focused agent-cli tests**

Run: `uv run pytest tests/agentcli/test_input_schema.py tests/agentcli/test_source_guard.py -v`

Expected: PASS.

- [ ] **Step 9: Commit the boundary work**

```bash
git add loop_apidoc/agentcli/input_schema.py loop_apidoc/agentcli/source_guard.py \
  tests/agentcli/test_input_schema.py tests/agentcli/test_source_guard.py
git commit -m "feat: accept schema field citations"
```

## Task 2: Normalize field citations into typed plan evidence

**Files:**
- Modify: `loop_apidoc/plan/models.py:15-65`
- Modify: `loop_apidoc/plan/builder.py:180-335`
- Modify: `tests/plan/test_builder.py`

**Interfaces:**
- Consumes: stage-07 schema dictionaries whose fields optionally carry `source`.
- Produces: `SchemaFieldEvidence(name: str, status: PlanItemStatus, citations: list[SourceCitation])` in `SchemaEntry.field_evidence`.

- [ ] **Step 1: Write the failing normalization test**

Add a focused test to `tests/plan/test_builder.py` that builds a two-source manifest and stage-07 extraction answer containing:

```python
{"name": "Payment", "source": "a.md#payment", "fields": [
    {"name": "amount", "type": "integer", "source": "b.md#amount"},
]}
```

Assert the resulting schema has one evidence record, with `name == "amount"`,
`status is PlanItemStatus.SUPPORTED`, and citation `manifest_source == "b.md"`.

- [ ] **Step 2: Run the normalization test to verify it fails**

Run: `uv run pytest tests/plan/test_builder.py -k field_evidence -v`

Expected: FAIL because `SchemaEntry` has no `field_evidence`.

- [ ] **Step 3: Define the typed record and plan field**

In `loop_apidoc/plan/models.py`, add:

```python
class SchemaFieldEvidence(_Cited):
    name: str


class SchemaEntry(_Cited):
    name: str | None = None
    fields: list[dict] = Field(default_factory=list)
    field_evidence: list[SchemaFieldEvidence] = Field(default_factory=list)
    enums: list = Field(default_factory=list)
    constraints: str | None = None
```

- [ ] **Step 4: Build evidence at the stage-07 boundary**

Add a pure `_schema_field_evidence(item, art, manifest)` helper in
`loop_apidoc/plan/builder.py`. For every dictionary in `item.get("fields") or []`
with a non-empty string `source` and a non-empty string `name`, call
`classify_item(source, query_id=art.query_id, answer_path=art.answer_path, manifest=manifest)`
and return `SchemaFieldEvidence(name=name, status=status, citations=[citation])`.

Update the stage-07 factory to receive the helper result. When any record is
`UNVERIFIED`, append `UnverifiedItem(area=f"07.schemas.{schema_name}.fields.{field_name}", detail=source, query_id=art.query_id)`.
Do not create evidence for a missing/blank source and do not mutate the raw
`fields` list consumed by OpenAPI generation.

- [ ] **Step 5: Run the normalization test to verify it passes**

Run: `uv run pytest tests/plan/test_builder.py -k field_evidence -v`

Expected: PASS.

- [ ] **Step 6: Add and run the fail-closed case**

Add a second test with `source: "outside.md#amount"` and a two-source manifest.
Assert `field_evidence[0].status is PlanItemStatus.UNVERIFIED` and one
`plan.unverified_items` entry has area `07.schemas.Payment.fields.amount`.

Run: `uv run pytest tests/plan/test_builder.py -k field_evidence -v`

Expected: PASS.

- [ ] **Step 7: Commit the plan-evidence work**

```bash
git add loop_apidoc/plan/models.py loop_apidoc/plan/builder.py tests/plan/test_builder.py
git commit -m "feat: normalize schema field evidence"
```

## Task 3: Emit field provenance and validate exact property claims

**Files:**
- Modify: `loop_apidoc/generate/provenance.py:1-105`
- Modify: `loop_apidoc/validate/speculation.py:1-70`
- Modify: `tests/generate/test_provenance.py`
- Modify: `tests/validate/test_speculation.py`

**Interfaces:**
- Consumes: `SchemaEntry.field_evidence` and generated OpenAPI schema property trees.
- Produces: property provenance target strings and no-speculation issues at exact property locations.

- [ ] **Step 1: Write the failing direct/nested/array provenance test**

Add a `SchemaEntry(name="Order", fields=[...], field_evidence=[...])` fixture in
`tests/generate/test_provenance.py` with evidence for `amount`, `customer.id`,
and `items[].sku`. Assert `build_provenance(plan)` includes:

```python
"components.schemas.Order.properties.amount"
"components.schemas.Order.properties.customer.properties.id"
"components.schemas.Order.properties.items.items.properties.sku"
```

and that each target's entry retains its own manifest source and locator.

- [ ] **Step 2: Run the provenance test to verify it fails**

Run: `uv run pytest tests/generate/test_provenance.py -k field_evidence -v`

Expected: FAIL because no property-level provenance is emitted.

- [ ] **Step 3: Implement deterministic field target mapping**

In `loop_apidoc/generate/provenance.py`, add a pure helper:

```python
def _field_target(schema_key: str, name: str) -> str | None:
    # Return None for empty names or segments made empty after removing [].
    # For every segment append `.properties.<segment>`.
    # Append `.items` after a non-terminal `[]` segment.
```

For each schema field-evidence record, call `_entries(target, evidence)` when
the helper returns a target. Use `schema_key_map(plan.schemas)` to keep the
target aligned with collision-safe component names.

- [ ] **Step 4: Run the provenance test to verify it passes**

Run: `uv run pytest tests/generate/test_provenance.py -k field_evidence -v`

Expected: PASS.

- [ ] **Step 5: Write failing speculation tests**

In `tests/validate/test_speculation.py`, add a document whose `components.schemas.Order`
contains a supported `amount` property and parent schema provenance is supported.
Provide only an unverified property provenance entry and assert one
`SOURCE_UNVERIFIED` issue has location
`components.schemas.Order.properties.amount`. Add a companion test with no
property provenance and supported parent-schema provenance; assert no issue for
that property.

- [ ] **Step 6: Run the speculation tests to verify they fail**

Run: `uv run pytest tests/validate/test_speculation.py -k schema_property -v`

Expected: the unverified-property test fails because the validator does not yet
enumerate properties; the fallback test may already pass but must remain as the
regression assertion.

- [ ] **Step 7: Implement property traversal and parent fallback**

Extend `_asserted_targets` in `loop_apidoc/validate/speculation.py` with a pure
recursive property walker. For each object `properties` mapping, emit its exact
`.properties.<name>` target; recurse into the property node and into any array
`items` node using `.items`. In `check_speculation`, when the exact property
target has no provenance, derive its parent schema target by trimming segments
from the first `.properties.` onward and use that parent entry's statuses. Do
not apply this fallback to paths, webhooks, security schemes, or top-level
schema targets.

- [ ] **Step 8: Run provenance and speculation suites**

Run: `uv run pytest tests/generate/test_provenance.py tests/validate/test_speculation.py -v`

Expected: PASS.

- [ ] **Step 9: Commit provenance and validation work**

```bash
git add loop_apidoc/generate/provenance.py loop_apidoc/validate/speculation.py \
  tests/generate/test_provenance.py tests/validate/test_speculation.py
git commit -m "feat: trace schema fields to property provenance"
```

## Task 4: Document extraction contract and close #18 as delivered

**Files:**
- Modify: `skills/loop-apidoc/reference/extraction-schemas.md`
- Verify: `README.md:177-190`
- Verify: `README.en.md:184-197`
- External update: GitHub issue `CarlLee1983/loop-apidoc#18`

**Interfaces:**
- Consumes: the stable `FieldEntry.source` extraction contract and existing single-file manifest behavior.
- Produces: agent guidance that asks for field citations when sources distinguish properties, plus an issue closure explaining the supported exact-file workflow.

- [ ] **Step 1: Add the documented field citation shape**

Update the schema-field example and field-key reference in
`skills/loop-apidoc/reference/extraction-schemas.md` to show:

```json
{
  "name": "amount",
  "type": "integer",
  "required": true,
  "description": "Transaction amount",
  "source": "api.md#request-body"
}
```

State that `source` is optional, must name a manifest source in multi-source
runs, and is emitted as provenance for the generated OpenAPI property.

- [ ] **Step 2: Verify the manifest documentation is already accurate**

Run: `rg -n -- '--sources.*sources-or-file|單一來源檔案|single source file' README.md README.en.md`

Expected: both README files describe `--sources <directory-or-file>` and explain
the parent directory / one-file manifest behavior. Do not modify them unless
the check fails.

- [ ] **Step 3: Run the documented behavior and focused regression tests**

Run: `uv run pytest tests/test_cli_manifest.py tests/agentcli/test_input_schema.py tests/agentcli/test_source_guard.py tests/plan/test_builder.py tests/generate/test_provenance.py tests/validate/test_speculation.py -v`

Expected: PASS.

- [ ] **Step 4: Commit documentation**

```bash
git add skills/loop-apidoc/reference/extraction-schemas.md
git commit -m "docs: document schema field citations"
```

- [ ] **Step 5: Close issue #18 with the delivered behavior**

After the preceding verification succeeds, post this comment to
`CarlLee1983/loop-apidoc#18` and close it as completed:

```markdown
Implemented via the more precise existing interface: `manifest --sources <file>`.

Passing a single source file makes its parent the `sources_root` and includes
only that file in the manifest. This covers selecting one target from a vendor
directory without adding a second glob-filtering semantic alongside excludes,
duplicate detection, and ignored-source reporting.
```

## Task 5: Full verification and close #17

**Files:**
- Verify: all files changed by Tasks 1–4.
- External update: GitHub issue `CarlLee1983/loop-apidoc#17`.

**Interfaces:**
- Consumes: all completed feature behavior.
- Produces: verified branch state and a completed issue record.

- [ ] **Step 1: Run lint**

Run: `uv run ruff check .`

Expected: `All checks passed!`.

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest`

Expected: all collected tests pass with zero failures.

- [ ] **Step 3: Inspect the final diff and status**

Run: `git diff HEAD~4..HEAD --check && git status --short --branch`

Expected: no whitespace errors; only intentional commits on the branch; no
uncommitted changes.

- [ ] **Step 4: Close issue #17 with verification evidence**

Post this comment to `CarlLee1983/loop-apidoc#17` and close it as completed:

```markdown
Implemented field-level schema evidence end to end.

`schemas[].fields[].source` is now accepted, checked against the manifest,
normalized into typed plan evidence, emitted as exact OpenAPI property
provenance, and enforced by no-speculation validation. Schema-level citations
remain the backwards-compatible fallback for fields without their own source.

Verified with `uv run ruff check .` and `uv run pytest`.
```

