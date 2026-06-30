# Developer Handoff Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a derived `handoff/` directory (integration checklist, Postman collection, SDK hints) on every `assemble` run, treating OpenAPI + integration-contract as the only contract sources.

**Architecture:** Add one new pure module `loop_apidoc/generate/handoff.py` exposing `build_handoff(openapi, plan, integration) -> dict[str, str]` (relative-path → content map). Wire it into `build_result`/`generate_outputs` exactly like `examples/`, add a `handoff` field to `GenerateResult`, and add a `review.html` product link. The module performs no file I/O and never re-reads generated files — it consumes the in-memory `openapi` dict, the `NormalizationPlan`, and the already-built `integration` dict.

**Tech Stack:** Python ≥3.11, pydantic v2, pyyaml, `uv`, `pytest`, `ruff`. Standard-library `json` only inside `handoff.py` (no new deps).

## Global Constraints

- **Derived-only / no fabrication:** handoff content comes solely from `openapi`, `NormalizationPlan`, and `integration-contract` data. Never invent sample values (`"string"`, `0`, `true`, fake amounts/tokens, guessed base URLs). Missing source values render as `<placeholder>` or as explicit blockers — copied verbatim from spec §Non-Goals.
- **No second contract:** never reprint full OpenAPI request/response schema definitions in any handoff file; link to the OpenAPI JSON pointer instead.
- **Pure functions:** `handoff.py` does no file I/O, does not re-read `openapi.yaml`, and does not parse files it caused to be generated. The only file-I/O exit remains `generate/` (`generate_outputs`), `run/`, and `diff/report.py`.
- **Always produced:** all three handoff files are written on every successful *and* validation-failed run (handoff has no dependency on `validation/report.json`; it only links to `../validation/report.md`).
- **OpenAPI pointers are JSON-pointer escaped and deterministic:** `~` → `~0` then `/` → `~1`; e.g. `/payments` → `../openapi.yaml#/paths/~1payments/post`; webhook `evt` → `../openapi.yaml#/webhooks/evt/post`.
- **Integration-contract pointers use array indexes in the generated document:** `../integration-contract.json#/crypto/0`, `#/callbacks/0`, `#/field_conditions/0`, `#/test_cases/0` — indexes align with list order in the integration dict (which preserves `plan.integration` list order).
- **Example links use the operationId directory convention:** `../examples/{operationId}/request.{sh,ts,py}`.
- **Language:** code comments and any `zh-TW` product strings follow repo convention; the handoff Markdown is developer-facing — keep section headings as in the spec example (English headings are acceptable; the spec example uses English).

---

## File Structure

- **Create** `loop_apidoc/generate/handoff.py` — pure builders: shared helpers (`_esc`, `_iter_operations`, `_op_identity`, `_contract_pointer`, `_snake`), plus `_build_sdk_hints`, `_build_integration_tasks`, `_build_postman_collection`, and the public `build_handoff`.
- **Create** `tests/generate/test_handoff_sdk_hints.py`
- **Create** `tests/generate/test_handoff_tasks.py`
- **Create** `tests/generate/test_handoff_postman.py`
- **Modify** `loop_apidoc/generate/models.py` — add `handoff: dict[str, str]` to `GenerateResult`.
- **Modify** `loop_apidoc/generate/writer.py` — call `build_handoff` in `build_result`; write `result.handoff` in `generate_outputs`.
- **Modify** `loop_apidoc/generate/__init__.py` — export `build_handoff`.
- **Modify** `loop_apidoc/generate/review.py:51-62` — add the `handoff/integration-tasks.md` product link.
- **Modify** `README.md:138-153` and `docs/ARCHITECTURE.md` — document the new `handoff/` directory as a derived engineering aid (not a contract source).

A note on data sources used by every builder:
- `openapi` dict — `info.title`, `servers`, `paths`, `webhooks`, `tags`, `components.securitySchemes`. Operations already carry `operationId`, `tags`, `security`, `parameters`, `requestBody`.
- `plan` (`NormalizationPlan`) — `missing_items`, `source_conflicts`, `unverified_items`, and `plan.integration` (an `IntegrationContract` with `crypto`/`callbacks`/`field_conditions`/`test_cases` whose `crypto[i].name`/`purpose` drive request-signing labels).
- `integration` dict (the `build_integration_document` result, or `None`) — used for its `missing` list and to confirm presence; pointer indexes match its list order.

---

## Task 1: Shared helpers + `sdk-hints.json` builder

**Files:**
- Create: `loop_apidoc/generate/handoff.py`
- Test: `tests/generate/test_handoff_sdk_hints.py`

**Interfaces:**
- Consumes: `openapi: dict`, `plan: NormalizationPlan` (from `loop_apidoc.plan.models`), `integration: dict | None`.
- Produces (relied on by Task 2/3/4):
  - `build_handoff(openapi: dict, plan: NormalizationPlan, integration: dict | None) -> dict[str, str]` — returns at least the key `"handoff/sdk-hints.json"` after this task.
  - Helpers: `_esc(s: str) -> str`; `_snake(name: str) -> str`; `_iter_operations(openapi: dict) -> Iterator[dict]` yielding `{"operation_id": str|None, "method": str (UPPER), "path": str|None, "op": dict, "webhook": str|None}`; `_op_identity(rec: dict) -> tuple[str, list[str]]` returning `(operation_id_or_fallback, generator_gaps)`; `_contract_pointer(rec: dict) -> str`; `_request_signing_labels(plan) -> list[str]` returning `["crypto:<name-or-index>", ...]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/generate/test_handoff_sdk_hints.py
from __future__ import annotations

import json

from loop_apidoc.generate.handoff import build_handoff
from loop_apidoc.plan.models import (
    CryptoScheme,
    IntegrationContract,
    NormalizationPlan,
    PlanItemStatus,
)


def _plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="n/a",
        integration=IntegrationContract(
            crypto=[CryptoScheme(status=PlanItemStatus.SUPPORTED, name="TradeInfo", purpose="request")]
        ),
    )


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Pay API", "version": "1.0"},
        "servers": [{"url": "https://api.example.com"}],
        "tags": [{"name": "Payments"}],
        "paths": {
            "/payments": {
                "post": {"operationId": "createPayment", "tags": ["Payments"]}
            }
        },
    }


def _hints(openapi: dict, plan: NormalizationPlan) -> dict:
    out = build_handoff(openapi, plan, {"crypto": [{"name": "TradeInfo"}], "missing": []})
    return json.loads(out["handoff/sdk-hints.json"])


def test_sdk_hints_top_level_keys():
    data = _hints(_openapi(), _plan())
    assert set(data) >= {"version", "contracts", "operation_groups", "implementation_notes", "gaps"}
    assert data["contracts"] == {
        "openapi": "../openapi.yaml",
        "integration": "../integration-contract.json",
    }


def test_sdk_hints_operation_note_shape():
    data = _hints(_openapi(), _plan())
    note = next(n for n in data["implementation_notes"] if n["operation_id"] == "createPayment")
    assert note["method"] == "POST"
    assert note["path"] == "/payments"
    assert note["contract_pointer"] == "../openapi.yaml#/paths/~1payments/post"
    assert "runtime:base_url" in note["requires"]
    assert "crypto:TradeInfo" in note["requires"]


def test_sdk_hints_groups_from_tags():
    data = _hints(_openapi(), _plan())
    group = next(g for g in data["operation_groups"] if g["name"] == "Payments")
    assert "createPayment" in group["operations"]


def test_sdk_hints_does_not_copy_schemas():
    blob = build_handoff(_openapi(), _plan(), {"crypto": [{"name": "TradeInfo"}], "missing": []})[
        "handoff/sdk-hints.json"
    ]
    assert "properties" not in blob
    assert "requestBody" not in blob
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/generate/test_handoff_sdk_hints.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.generate.handoff'`

- [ ] **Step 3: Write minimal implementation**

```python
# loop_apidoc/generate/handoff.py
from __future__ import annotations

import json
import re
from collections.abc import Iterator

from loop_apidoc.plan.models import NormalizationPlan

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def _esc(s: str) -> str:
    """JSON-pointer escape: ~ -> ~0 then / -> ~1 (order matters)."""
    return s.replace("~", "~0").replace("/", "~1")


def _snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name.strip())
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return re.sub(r"_+", "_", s) or "value"


def _iter_operations(openapi: dict) -> Iterator[dict]:
    for path, item in (openapi.get("paths") or {}).items():
        for method, op in (item or {}).items():
            if method.lower() in _HTTP_METHODS and isinstance(op, dict):
                yield {
                    "operation_id": op.get("operationId"),
                    "method": method.upper(),
                    "path": path,
                    "op": op,
                    "webhook": None,
                }
    for name, item in (openapi.get("webhooks") or {}).items():
        for method, op in (item or {}).items():
            if method.lower() in _HTTP_METHODS and isinstance(op, dict):
                yield {
                    "operation_id": op.get("operationId"),
                    "method": method.upper(),
                    "path": None,
                    "op": op,
                    "webhook": name,
                }


def _op_identity(rec: dict) -> tuple[str, list[str]]:
    """Return (operationId-or-deterministic-fallback, generator_gaps)."""
    oid = rec["operation_id"]
    if oid:
        return oid, []
    base = rec["webhook"] or rec["path"] or "operation"
    fallback = _snake(f"{rec['method']}_{base}")
    return fallback, [
        f"generator: operation {rec['method']} {base} has no operationId; used fallback {fallback}"
    ]


def _contract_pointer(rec: dict) -> str:
    if rec["webhook"] is not None:
        return f"../openapi.yaml#/webhooks/{_esc(rec['webhook'])}/{rec['method'].lower()}"
    return f"../openapi.yaml#/paths/{_esc(rec['path'])}/{rec['method'].lower()}"


def _request_signing_labels(plan: NormalizationPlan) -> list[str]:
    """`crypto:<name>` labels for request/signature-purpose schemes (mirrors examples.py)."""
    contract = plan.integration
    if contract is None:
        return []
    labels: list[str] = []
    for idx, s in enumerate(contract.crypto):
        if s.purpose in (None, "request", "signature"):
            labels.append(f"crypto:{s.name or idx}")
    return labels


def _operation_groups(openapi: dict) -> list[dict]:
    """One group per OpenAPI tag (first-appearance order); untagged ops -> 'Ungrouped'."""
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for rec in _iter_operations(openapi):
        oid, _ = _op_identity(rec)
        tags = rec["op"].get("tags") or ["Ungrouped"]
        for tag in tags:
            if tag not in groups:
                groups[tag] = []
                order.append(tag)
            if oid not in groups[tag]:
                groups[tag].append(oid)
    return [{"name": tag, "operations": groups[tag]} for tag in order]


def _build_sdk_hints(openapi: dict, plan: NormalizationPlan) -> str:
    crypto_labels = _request_signing_labels(plan)
    notes: list[dict] = []
    gaps: list[str] = []
    for rec in _iter_operations(openapi):
        oid, op_gaps = _op_identity(rec)
        gaps.extend(op_gaps)
        notes.append(
            {
                "operation_id": oid,
                "method": rec["method"],
                "path": rec["path"] if rec["path"] is not None else f"webhook:{rec['webhook']}",
                "contract_pointer": _contract_pointer(rec),
                "example_paths": (
                    [f"../examples/{oid}/request.ts"] if rec["operation_id"] else []
                ),
                "requires": ["runtime:base_url", *crypto_labels],
                "gaps": op_gaps,
            }
        )
    doc = {
        "version": "1.0",
        "contracts": {
            "openapi": "../openapi.yaml",
            "integration": "../integration-contract.json",
        },
        "operation_groups": _operation_groups(openapi),
        "implementation_notes": notes,
        "gaps": gaps,
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def build_handoff(
    openapi: dict, plan: NormalizationPlan, integration: dict | None
) -> dict[str, str]:
    return {"handoff/sdk-hints.json": _build_sdk_hints(openapi, plan)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/generate/test_handoff_sdk_hints.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/handoff.py tests/generate/test_handoff_sdk_hints.py
git commit -m "feat: [generate] add handoff sdk-hints builder + shared helpers"
```

---

## Task 2: `integration-tasks.md` builder

**Files:**
- Modify: `loop_apidoc/generate/handoff.py`
- Test: `tests/generate/test_handoff_tasks.py`

**Interfaces:**
- Consumes: helpers from Task 1 (`_iter_operations`, `_op_identity`, `_contract_pointer`), plus `openapi.servers`, `openapi.components.securitySchemes`, `plan.integration.crypto[*].key_source`, `plan.missing_items`, `plan.source_conflicts`, `plan.unverified_items`, and `integration["missing"]`.
- Produces: `build_handoff` now also returns key `"handoff/integration-tasks.md"`. New helper `_build_integration_tasks(openapi, plan, integration) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/generate/test_handoff_tasks.py
from __future__ import annotations

from loop_apidoc.generate.handoff import build_handoff
from loop_apidoc.plan.models import (
    CryptoScheme,
    IntegrationContract,
    KeySource,
    MissingItem,
    NormalizationPlan,
    PlanItemStatus,
    SourceConflict,
)


def _plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="n/a",
        missing_items=[MissingItem(area="crypto", detail="source does not state AES padding for TradeInfo")],
        source_conflicts=[SourceConflict(area="auth", detail="two base URLs disagree")],
        integration=IntegrationContract(
            crypto=[
                CryptoScheme(
                    status=PlanItemStatus.SUPPORTED,
                    name="TradeInfo",
                    purpose="request",
                    key_source=KeySource(key="HASH_KEY", iv="HASH_IV"),
                )
            ]
        ),
    )


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Pay API", "version": "1.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {"/payments": {"post": {"operationId": "createPayment"}}},
        "components": {
            "securitySchemes": {"merchantKey": {"type": "apiKey", "in": "header", "name": "X-Key"}}
        },
    }


def _tasks() -> str:
    return build_handoff(_openapi(), _plan(), {"crypto": [{"name": "TradeInfo"}], "missing": []})[
        "handoff/integration-tasks.md"
    ]


def test_tasks_run_context_links():
    md = _tasks()
    assert "../openapi.yaml" in md
    assert "../integration-contract.json" in md
    assert "../validation/report.md" in md


def test_tasks_implementation_order_has_pointer():
    md = _tasks()
    assert "createPayment" in md
    assert "../openapi.yaml#/paths/~1payments/post" in md


def test_tasks_runtime_config_base_url_and_auth():
    md = _tasks()
    assert "base_url" in md
    assert "merchantKey" in md  # auth variable from security scheme


def test_tasks_crypto_and_blockers():
    md = _tasks()
    assert "../integration-contract.json#/crypto/0" in md
    assert "Conflict" in md  # source_conflicts
    assert "Blocked" in md   # missing_items
    assert "AES padding" in md


def test_tasks_no_schema_tables():
    md = _tasks()
    # navigation only — never a request-body field table / response schema copy
    assert "properties" not in md
    assert "| Field | Type |" not in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/generate/test_handoff_tasks.py -v`
Expected: FAIL with `KeyError: 'handoff/integration-tasks.md'`

- [ ] **Step 3: Write minimal implementation**

Add these helpers to `loop_apidoc/generate/handoff.py` (after `_operation_groups`):

```python
def _base_url_initial(openapi: dict) -> str:
    servers = openapi.get("servers") or []
    return (servers[0].get("url") if servers else None) or "<base_url>"


def _runtime_config_lines(openapi: dict, plan: NormalizationPlan) -> list[str]:
    lines = [f"- [ ] `base_url` — initial value: `{_base_url_initial(openapi)}`"]
    schemes = ((openapi.get("components") or {}).get("securitySchemes") or {})
    for name, scheme in schemes.items():
        kind = scheme.get("type", "")
        where = scheme.get("name") or scheme.get("scheme") or scheme.get("in") or ""
        suffix = f" ({where})" if where else ""
        lines.append(f"- [ ] Auth `{name}` — {kind}{suffix}")
    contract = plan.integration
    if contract is not None:
        for idx, s in enumerate(contract.crypto):
            ks = s.key_source
            if ks and (ks.key or ks.iv):
                parts = [p for p in (ks.key and f"key=`{ks.key}`", ks.iv and f"iv=`{ks.iv}`") if p]
                lines.append(
                    f"- [ ] Secret for `{s.name or idx}` — {', '.join(parts)} "
                    f"(`../integration-contract.json#/crypto/{idx}`)"
                )
    return lines


def _implementation_order_lines(openapi: dict, plan: NormalizationPlan) -> list[str]:
    crypto_labels = _request_signing_labels(plan)
    lines: list[str] = []
    for rec in _iter_operations(openapi):
        oid, _ = _op_identity(rec)
        ident = (
            f"`{oid}` (`{rec['method']} {rec['path']}`)"
            if rec["path"] is not None
            else f"`{oid}` (webhook `{rec['webhook']}` receiver)"
        )
        lines.append(f"- [ ] Implement {ident}")
        lines.append(f"  - Contract: `{_contract_pointer(rec)}`")
        if rec["operation_id"]:
            lines.append(f"  - Example: `../examples/{oid}/request.ts`")
        for label in crypto_labels:
            lines.append(f"  - Requires {label}")
    if not lines:
        lines.append("- No source-grounded operations were found.")
    return lines


def _mechanism_lines(plan: NormalizationPlan) -> list[str]:
    contract = plan.integration
    if contract is None:
        return ["- Integration contract not present for this run."]
    lines: list[str] = []
    for idx, s in enumerate(contract.crypto):
        lines.append(
            f"- [ ] Signing/encryption `{s.name or idx}` "
            f"(`../integration-contract.json#/crypto/{idx}`)"
        )
    for idx, cb in enumerate(contract.callbacks):
        lines.append(
            f"- [ ] Callback `{cb.name or idx}` "
            f"(`../integration-contract.json#/callbacks/{idx}`)"
        )
    for idx, _cond in enumerate(contract.field_conditions):
        lines.append(
            f"- [ ] Field condition #{idx} "
            f"(`../integration-contract.json#/field_conditions/{idx}`)"
        )
    if not lines:
        lines.append(
            "- No source-grounded signing, encryption, callback, condition, or "
            "test-case mechanisms were found."
        )
    return lines


def _blocker_lines(plan: NormalizationPlan, integration: dict | None) -> list[str]:
    lines: list[str] = []
    for m in plan.missing_items:
        lines.append(f"- [ ] Blocked: {m.area} — {m.detail}")
    for c in plan.source_conflicts:
        lines.append(f"- [ ] Conflict: {c.area} — {c.detail}")
    for u in plan.unverified_items:
        lines.append(f"- [ ] Unverified: {u.area} — {u.detail}")
    for gap in (integration or {}).get("missing", []) or []:
        lines.append(f"- [ ] Gap: {gap.get('area')} — {gap.get('detail')}")
    if not lines:
        lines.append("- No outstanding blockers, conflicts, unverified items, or gaps.")
    return lines


def _build_integration_tasks(
    openapi: dict, plan: NormalizationPlan, integration: dict | None
) -> str:
    parts = [
        "# Developer Integration Tasks",
        "",
        "Derived navigation aid — NOT a contract. See `../openapi.yaml` for the schema.",
        "",
        "## Run Context",
        "",
        "- Primary contract: `../openapi.yaml`",
        "- Integration mechanisms: `../integration-contract.json`",
        "- Validation status: `../validation/report.md`",
        "- Request examples: `../examples/README.md`",
        "",
        "## Runtime Configuration",
        "",
        *_runtime_config_lines(openapi, plan),
        "",
        "## Implementation Order",
        "",
        *_implementation_order_lines(openapi, plan),
        "",
        "## Integration Mechanisms",
        "",
        *_mechanism_lines(plan),
        "",
        "## Blockers & Gaps",
        "",
        *_blocker_lines(plan, integration),
    ]
    return "\n".join(parts) + "\n"
```

Then extend `build_handoff` to include the new key:

```python
def build_handoff(
    openapi: dict, plan: NormalizationPlan, integration: dict | None
) -> dict[str, str]:
    return {
        "handoff/integration-tasks.md": _build_integration_tasks(openapi, plan, integration),
        "handoff/sdk-hints.json": _build_sdk_hints(openapi, plan),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/generate/test_handoff_tasks.py tests/generate/test_handoff_sdk_hints.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/handoff.py tests/generate/test_handoff_tasks.py
git commit -m "feat: [generate] add handoff integration-tasks.md builder"
```

---

## Task 3: `postman_collection.json` builder

**Files:**
- Modify: `loop_apidoc/generate/handoff.py`
- Test: `tests/generate/test_handoff_postman.py`

**Interfaces:**
- Consumes: helpers from Task 1, plus `openapi.info.title`, `openapi.servers`, per-operation `parameters` and `requestBody`.
- Produces: `build_handoff` now also returns key `"handoff/postman_collection.json"`. New helpers `_param_value(name, node) -> object` (source value or `<placeholder>`, never a type sample) and `_build_postman_collection(openapi, plan) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/generate/test_handoff_postman.py
from __future__ import annotations

import json

from loop_apidoc.generate.handoff import build_handoff
from loop_apidoc.plan.models import NormalizationPlan


def _plan() -> NormalizationPlan:
    return NormalizationPlan(notebook_url="n/a")


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Pay API", "version": "1.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/payments": {
                "post": {
                    "operationId": "createPayment",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "properties": {
                                        "amount": {"type": "integer"},
                                        "currency": {"type": "string", "enum": ["TWD"]},
                                    }
                                }
                            }
                        }
                    },
                }
            }
        },
    }


def _collection() -> dict:
    out = build_handoff(_openapi(), _plan(), None)
    return json.loads(out["handoff/postman_collection.json"])


def test_postman_v21_top_level_shape():
    c = _collection()
    assert c["info"]["name"] == "Pay API"
    assert c["info"]["schema"] == (
        "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    )
    assert isinstance(c["item"], list)
    base = next(v for v in c["variable"] if v["key"] == "base_url")
    assert base["value"] == "https://api.example.com"


def test_postman_url_uses_base_url_variable():
    c = _collection()
    item = c["item"][0]
    assert "{{base_url}}" in item["request"]["url"]["raw"]


def test_postman_description_has_openapi_pointer():
    c = _collection()
    item = c["item"][0]
    assert "../openapi.yaml#/paths/~1payments/post" in item["description"]


def test_postman_missing_values_are_placeholders_not_samples():
    c = _collection()
    body_raw = c["item"][0]["request"]["body"]["raw"]
    parsed = json.loads(body_raw)
    assert parsed["amount"] == "<amount>"        # no guessed integer 0
    assert parsed["currency"] == "TWD"           # single-enum is source-stated
    assert "string" not in body_raw              # no fabricated "string" sample
    assert ": 0" not in body_raw and "true" not in body_raw


def test_postman_no_prerequest_script():
    c = _collection()
    assert "event" not in c["item"][0]


def test_postman_title_fallback_when_missing():
    op = _openapi()
    op["info"] = {}
    out = build_handoff(op, _plan(), None)
    c = json.loads(out["handoff/postman_collection.json"])
    assert c["info"]["name"] == "Untitled API"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/generate/test_handoff_postman.py -v`
Expected: FAIL with `KeyError: 'handoff/postman_collection.json'`

- [ ] **Step 3: Write minimal implementation**

Add to `loop_apidoc/generate/handoff.py`:

```python
def _param_value(name: str, node: dict) -> object:
    """Source value only (example / single-enum / const / default); else `<name>`.

    Mirrors examples._resolve_value — never derives a type-based sample, so we
    never emit fabricated "string"/0/true placeholders.
    """
    if isinstance(node, dict) and "example" in node:
        return node["example"]
    schema = node.get("schema") if isinstance(node.get("schema"), dict) else node
    if isinstance(schema, dict):
        if "example" in schema:
            return schema["example"]
        enum = schema.get("enum")
        if isinstance(enum, list) and len(enum) == 1:
            return enum[0]
        if "const" in schema:
            return schema["const"]
        if "default" in schema:
            return schema["default"]
    return f"<{_snake(name)}>"


def _postman_item(rec: dict, plan: NormalizationPlan) -> dict:
    oid, _ = _op_identity(rec)
    op = rec["op"]
    path = rec["path"] or ""
    segments = [seg for seg in path.split("/") if seg]
    headers = []
    query = []
    for raw in op.get("parameters", []) or []:
        loc = raw.get("in")
        value = _param_value(raw.get("name", ""), raw)
        if loc == "header":
            headers.append({"key": raw.get("name"), "value": value})
        elif loc == "query":
            query.append({"key": raw.get("name"), "value": value})
    url = {"raw": "{{base_url}}" + path, "host": ["{{base_url}}"], "path": segments}
    if query:
        url["query"] = query
    request: dict = {"method": rec["method"], "header": headers, "url": url}
    body = (op.get("requestBody") or {}).get("content") or {}
    if body:
        content_type = next(iter(body))
        schema = body[content_type].get("schema", {}) or {}
        fields = {
            pname: _param_value(pname, {"schema": pnode})
            for pname, pnode in (schema.get("properties") or {}).items()
        }
        request["body"] = {
            "mode": "raw",
            "raw": json.dumps(fields, ensure_ascii=False, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    desc_lines = [f"OpenAPI: `{_contract_pointer(rec)}`"]
    if rec["operation_id"]:
        desc_lines.append(f"Example: `../examples/{oid}/request.ts`")
    contract = plan.integration
    if contract is not None and contract.crypto:
        desc_lines.append(
            "Requires signing — see `../integration-contract.json#/crypto/0` "
            "(no pre-request script generated; implement crypto from the contract)."
        )
    return {"name": oid, "request": request, "description": "\n".join(desc_lines)}


def _build_postman_collection(openapi: dict, plan: NormalizationPlan) -> str:
    title = (openapi.get("info") or {}).get("title") or "Untitled API"
    doc = {
        "info": {
            "name": title,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [{"key": "base_url", "value": _base_url_initial(openapi)}],
        "item": [_postman_item(rec, plan) for rec in _iter_operations(openapi)],
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
```

Then extend `build_handoff`:

```python
def build_handoff(
    openapi: dict, plan: NormalizationPlan, integration: dict | None
) -> dict[str, str]:
    return {
        "handoff/integration-tasks.md": _build_integration_tasks(openapi, plan, integration),
        "handoff/postman_collection.json": _build_postman_collection(openapi, plan),
        "handoff/sdk-hints.json": _build_sdk_hints(openapi, plan),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/generate/test_handoff_postman.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/handoff.py tests/generate/test_handoff_postman.py
git commit -m "feat: [generate] add handoff postman collection builder"
```

---

## Task 4: Wire handoff into the generation pipeline + `review.html`

**Files:**
- Modify: `loop_apidoc/generate/models.py:22-28` (`GenerateResult`)
- Modify: `loop_apidoc/generate/writer.py:7-57` (`build_result`, `generate_outputs`)
- Modify: `loop_apidoc/generate/__init__.py:1-20` (export `build_handoff`)
- Modify: `loop_apidoc/generate/review.py:51-67` (`_artifact_links`)
- Test: `tests/generate/test_writer.py`, `tests/generate/test_review_html.py`

**Interfaces:**
- Consumes: `build_handoff` (Task 1–3).
- Produces: `GenerateResult.handoff: dict[str, str]`; `generate_outputs` writes every `handoff/*` relative path under `run_dir`; `review.html` contains a `handoff/integration-tasks.md` link.

- [ ] **Step 1: Write the failing tests**

Append to `tests/generate/test_writer.py` (reuse that file's existing `plan`/`manifest` construction helpers; if it builds them inline, mirror the same construction):

```python
def test_generate_outputs_writes_handoff(tmp_path):
    plan, manifest = _minimal_plan_and_manifest()  # use this file's existing helper
    run_dir = tmp_path / "run"
    result = generate_outputs(plan, manifest, run_dir)
    assert set(result.handoff) == {
        "handoff/integration-tasks.md",
        "handoff/postman_collection.json",
        "handoff/sdk-hints.json",
    }
    assert (run_dir / "handoff" / "integration-tasks.md").is_file()
    assert (run_dir / "handoff" / "postman_collection.json").is_file()
    assert (run_dir / "handoff" / "sdk-hints.json").is_file()
```

Append to `tests/generate/test_review_html.py`:

```python
def test_review_html_links_handoff():
    html = _build_review_html_for_minimal_plan()  # use this file's existing helper
    assert "handoff/integration-tasks.md" in html
```

> If these test files construct the plan/manifest differently, copy that file's existing setup verbatim rather than inventing a helper name.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/generate/test_writer.py -k handoff tests/generate/test_review_html.py -k handoff -v`
Expected: FAIL — `AttributeError: 'GenerateResult' object has no attribute 'handoff'` and missing-link assertion.

- [ ] **Step 3: Write minimal implementation**

In `loop_apidoc/generate/models.py`, add the field to `GenerateResult`:

```python
class GenerateResult(BaseModel):
    openapi: dict
    markdown: str
    provenance: ProvenanceDocument
    integration: dict | None = None
    examples: dict[str, str] = Field(default_factory=dict)
    handoff: dict[str, str] = Field(default_factory=dict)
    review_html: str = ""
```

In `loop_apidoc/generate/writer.py`, import and call `build_handoff` in `build_result`, then write the map in `generate_outputs`:

```python
from loop_apidoc.generate.handoff import build_handoff
```

```python
def build_result(plan: NormalizationPlan, manifest: Manifest) -> GenerateResult:
    openapi = build_openapi(plan)
    integration = build_integration_document(plan)
    result = GenerateResult(
        openapi=openapi,
        markdown=build_markdown(plan, manifest),
        provenance=build_provenance(plan),
        integration=integration,
        examples=build_examples(openapi, plan),
        handoff=build_handoff(openapi, plan, integration),
    )
    return result.model_copy(update={
        "review_html": build_review_html(plan, manifest, result)
    })
```

Add the writer loop in `generate_outputs` (after the `examples` loop, before `return result`):

```python
    for relpath, content in result.handoff.items():
        target = run_dir / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return result
```

In `loop_apidoc/generate/__init__.py`, export `build_handoff`:

```python
from loop_apidoc.generate.handoff import build_handoff
```

and add `"build_handoff"` to `__all__`.

In `loop_apidoc/generate/review.py`, add the handoff link inside `_artifact_links` (after the examples link, before `return`):

```python
    if result.handoff:
        links.append(("開發交接", "handoff/integration-tasks.md", "handoff/integration-tasks.md"))
```

- [ ] **Step 4: Run the full generate test suite to verify it passes**

Run: `uv run pytest tests/generate -v`
Expected: PASS (all generate tests, including the two new assertions).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/models.py loop_apidoc/generate/writer.py loop_apidoc/generate/__init__.py loop_apidoc/generate/review.py tests/generate/test_writer.py tests/generate/test_review_html.py
git commit -m "feat: [generate] wire handoff pack into generate_outputs + review.html"
```

---

## Task 5: Documentation + full verification + manual spot-check

**Files:**
- Modify: `README.md:138-153` (run-dir tree)
- Modify: `docs/ARCHITECTURE.md` (generate-stage artifact row + package-boundary note)

**Interfaces:** none (docs + verification only).

- [ ] **Step 1: Update README run-dir tree**

In `README.md`, add the `handoff/` block to the run-dir tree (immediately after the `examples/` line at `README.md:146`):

```text
    ├── handoff/                    # 開發交接輔助(衍生產物,非契約來源)
    │   ├── integration-tasks.md    # 實作順序/執行設定/阻塞項檢查表
    │   ├── postman_collection.json # Postman v2.1 請求形狀集合(可匯入)
    │   └── sdk-hints.json          # 精簡 SDK/client 生成提示(不複製 schema)
```

Also add one clarifying sentence after the tree (near `README.md:154`): `handoff/` 為衍生的工程導引與工具轉接產物,**契約來源仍是 `openapi.yaml` 與 `integration-contract.json`**,不重複 schema。

- [ ] **Step 2: Update ARCHITECTURE.md**

In `docs/ARCHITECTURE.md`, update the generate-stage artifact row (`docs/ARCHITECTURE.md:84`) to append `、handoff/`, and add one sentence to the generate description noting: `handoff/`(`integration-tasks.md`/`postman_collection.json`/`sdk-hints.json`)為衍生工程導引,由 `build_handoff(openapi, plan, integration)` 純函式產出,不做檔案 I/O、不重讀 `openapi.yaml`、不複製 schema;契約來源仍為 OpenAPI 與 integration-contract。

- [ ] **Step 3: Run full verification**

Run: `uv run pytest`
Expected: PASS (whole suite green).

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 4: Manual spot-check on a signing/callback benchmark**

Run an `assemble` against a benchmark with signing + callback data (e.g. `newebpay-mpg`, per the benchmark-validation memory), then inspect:

```bash
ls output/<run-id>/handoff/
```

Confirm by eye:
- `integration-tasks.md` — checklist is useful: run-context links resolve, implementation-order items carry OpenAPI pointers and example links, crypto/callback tasks and blockers appear; no request-body field tables or response-schema copies.
- `postman_collection.json` — imports into Postman without error; URLs use `{{base_url}}`; missing values are `<placeholder>`s, not fabricated samples; no pre-request scripts.
- `sdk-hints.json` — compact, links to both contracts, groups operations, lists `requires`/`gaps`, and contains no copied schemas.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/ARCHITECTURE.md
git commit -m "docs: [handoff] document derived developer handoff pack output"
```

---

## Self-Review

**1. Spec coverage**
- Goals 1–6 → Tasks 1–4 (generate three files by default, derived-only, implementation guidance, Postman adapter, sdk-hints, pure-function/single-I/O-exit wiring). ✓
- Artifact details (`integration-tasks.md` sections 1–5, Postman v2.1 rules, sdk-hints allowed/disallowed) → Tasks 2/3 with section-by-section helpers. ✓
- Pointer rules (JSON-pointer escape, integration array indexes, example dirs) → `_esc` / `_contract_pointer` / `#/crypto/{i}` in Tasks 1–3. ✓
- Edge cases: no operations (empty `item`/notes, "no source-grounded operations" line) ✓; no base URL (`<base_url>` + runtime task) ✓; no integration mechanisms ("none found" line) ✓; validation failure (handoff has no validation dep, links to `report.md`; writer runs handoff before validation) ✓; missing operationId (`_op_identity` fallback + generator gap in sdk-hints) ✓; webhooks (`_iter_operations` yields webhooks, `#/webhooks/...` pointer, receiver task) ✓.
- Testing strategy: three named test files created with the spec's assertions, plus writer/review integration tests. ✓
- Acceptance criteria: three files every run ✓; derived-only ✓; no full schema copy (asserted) ✓; placeholders/blockers ✓; review entry point ✓; README + ARCHITECTURE docs (Task 5) ✓; `pytest`/`ruff` (Task 5 Step 3) ✓; benchmark spot-check (Task 5 Step 4) ✓.

**2. Placeholder scan** — every code step contains complete, runnable code; no "TBD"/"add error handling"/"similar to Task N". The only deliberate `<...>` strings are the spec-mandated source-missing placeholders. ✓

**3. Type consistency** — `build_handoff(openapi, plan, integration)` signature is identical across Tasks 1–4; `_iter_operations` yields the same dict shape consumed by `_op_identity`/`_contract_pointer`/`_postman_item`; `GenerateResult.handoff` matches the `dict[str, str]` returned by `build_handoff` and iterated in `generate_outputs`; `_base_url_initial` (defined Task 2) reused in Task 3. ✓
