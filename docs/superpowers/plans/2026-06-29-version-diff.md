# Run Version Diff Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `loop-apidoc diff --base <old-run> --head <new-run>` to compare two completed run directories and emit deterministic JSON/Markdown change reports grouped by downstream impact.

**Architecture:** Add a focused `loop_apidoc/diff/` package. `loader.py` reads validated run artifacts, `compare.py` produces structured findings, `models.py` owns report models, and `report.py` renders/writes reports. `cli.py` only wires Typer arguments, exit code `2` input failures, and output paths.

**Tech Stack:** Python 3.11+, Typer, pydantic v2, PyYAML, pytest, `uv`. No new runtime or dev dependencies.

---

## Scope And Constraints

- Compare generated run outputs only: `openapi.yaml`, `integration-contract.json`, `provenance.json`, `validation/report.json`, and `manifest.json`.
- Do not compare `api-guide.zh-TW.md` or generated `examples/` in the first implementation.
- Do not add semantic-version recommendations.
- Do not make network calls.
- Do not mutate either input run directory until both run directories load successfully.
- A breaking finding is still a successful command result. The CLI exits `0` when reports are written, regardless of finding impact.
- Invalid inputs exit `2` and leave no newly-created report directory.

## File Structure

| File | Responsibility | Change |
| --- | --- | --- |
| `loop_apidoc/diff/__init__.py` | Public package exports | Create; export models, loader, compare/report entry points. |
| `loop_apidoc/diff/models.py` | Diff enums and pydantic models | Create `DiffImpact`, `DiffFinding`, `DiffReport`. |
| `loop_apidoc/diff/loader.py` | Run artifact loading and fail-loud input errors | Create `DiffInputError`, `RunArtifacts`, `load_run_artifacts`. |
| `loop_apidoc/diff/compare.py` | Deterministic artifact comparison | Create `build_diff_report` plus private helpers. |
| `loop_apidoc/diff/report.py` | JSON/Markdown rendering and report writing | Create `render_markdown` and `write_reports`. |
| `loop_apidoc/cli.py` | User-facing command registration | Add `diff` command only; no comparison logic. |
| `tests/diff/test_loader.py` | Loader unit tests | New tests for loading and input failure. |
| `tests/diff/test_compare_openapi.py` | OpenAPI impact tests | New tests for endpoint, parameter, schema, response, security impact. |
| `tests/diff/test_compare_supporting_artifacts.py` | Integration/provenance/validation/manifest tests | New tests for non-OpenAPI artifacts. |
| `tests/diff/test_report.py` | Markdown/JSON report writer tests | New tests for stable rendering and writes. |
| `tests/test_cli_diff.py` | CLI smoke tests | New Typer tests for default output, override output, and input failure. |
| `README.md` | CLI usage docs | Add concise `diff` command section. |

## Task 1: Models And Run Artifact Loader

**Files:**
- Create: `loop_apidoc/diff/__init__.py`
- Create: `loop_apidoc/diff/models.py`
- Create: `loop_apidoc/diff/loader.py`
- Create: `tests/diff/test_loader.py`

- [ ] **Step 1: Write failing loader tests**

Create `tests/diff/test_loader.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from loop_apidoc.diff.loader import DiffInputError, load_run_artifacts
from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.validate.models import ValidationReport

_NOW = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "paths": {},
    }


def write_run(run_dir: Path, *, integration: dict | None = None) -> Path:
    run_dir.mkdir(parents=True)
    (run_dir / "openapi.yaml").write_text(
        yaml.safe_dump(_openapi(), sort_keys=False),
        encoding="utf-8",
    )
    provenance = ProvenanceDocument(
        notebook_url="",
        entries=[
            ProvenanceEntry(
                target="info.title",
                status=PlanItemStatus.SUPPORTED,
                manifest_source="manual.md",
                query_id="01",
                answer_path="answers/01.txt",
                locator="p.1",
            )
        ],
    )
    (run_dir / "provenance.json").write_text(
        provenance.model_dump_json(indent=2),
        encoding="utf-8",
    )
    validation_dir = run_dir / "validation"
    validation_dir.mkdir()
    (validation_dir / "report.json").write_text(
        ValidationReport().model_dump_json(indent=2),
        encoding="utf-8",
    )
    manifest = Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=10,
                sha256="abc",
                scanned_at=_NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )
    if integration is not None:
        (run_dir / "integration-contract.json").write_text(
            json.dumps(integration, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return run_dir


def test_load_run_artifacts_reads_required_and_optional_files(tmp_path):
    run_dir = write_run(
        tmp_path / "run",
        integration={"version": "1.0", "crypto": [{"name": "sig"}]},
    )

    artifacts = load_run_artifacts(run_dir)

    assert artifacts.run_dir == run_dir
    assert artifacts.openapi["info"]["title"] == "Demo"
    assert artifacts.integration == {"version": "1.0", "crypto": [{"name": "sig"}]}
    assert artifacts.provenance.entries[0].target == "info.title"
    assert artifacts.validation.ok is True
    assert artifacts.manifest.local_sources[0].relative_path == "manual.md"


def test_load_run_artifacts_allows_missing_integration_contract(tmp_path):
    artifacts = load_run_artifacts(write_run(tmp_path / "run"))
    assert artifacts.integration is None


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("openapi.yaml", "openapi.yaml"),
        ("provenance.json", "provenance.json"),
        ("validation/report.json", "validation/report.json"),
        ("manifest.json", "manifest.json"),
    ],
)
def test_load_run_artifacts_rejects_missing_required_artifact(
    tmp_path,
    relative_path,
    message,
):
    run_dir = write_run(tmp_path / "run")
    (run_dir / relative_path).unlink()

    with pytest.raises(DiffInputError) as excinfo:
        load_run_artifacts(run_dir)

    assert message in str(excinfo.value)


def test_load_run_artifacts_rejects_bad_yaml(tmp_path):
    run_dir = write_run(tmp_path / "run")
    (run_dir / "openapi.yaml").write_text("a: b:\n  - broken", encoding="utf-8")

    with pytest.raises(DiffInputError) as excinfo:
        load_run_artifacts(run_dir)

    assert "openapi.yaml" in str(excinfo.value)


def test_load_run_artifacts_rejects_non_object_integration(tmp_path):
    run_dir = write_run(tmp_path / "run")
    (run_dir / "integration-contract.json").write_text("[]", encoding="utf-8")

    with pytest.raises(DiffInputError) as excinfo:
        load_run_artifacts(run_dir)

    assert "integration-contract.json" in str(excinfo.value)
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/diff/test_loader.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.diff'`.

- [ ] **Step 3: Add diff models**

Create `loop_apidoc/diff/models.py`:

```python
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DiffImpact(str, Enum):
    BREAKING = "breaking"
    ADDITIVE = "additive"
    CHANGED = "changed"
    SOURCE_ONLY = "source_only"


class DiffFinding(BaseModel):
    impact: DiffImpact
    area: str
    location: str
    summary: str
    before: Any | None = None
    after: Any | None = None


class DiffReport(BaseModel):
    base_run: str
    head_run: str
    summary: dict[str, int]
    findings: list[DiffFinding] = Field(default_factory=list)
```

- [ ] **Step 4: Add loader**

Create `loop_apidoc/diff/loader.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.validate.models import ValidationReport


class DiffInputError(ValueError):
    """The run directory cannot be compared because an artifact is missing or invalid."""


@dataclass(frozen=True)
class RunArtifacts:
    run_dir: Path
    openapi: dict
    integration: dict | None
    provenance: ProvenanceDocument
    validation: ValidationReport
    manifest: Manifest


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise DiffInputError(f"required artifact missing: {label}")


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DiffInputError(f"cannot read {label}: {str(exc)[:200]}") from exc


def _load_json(path: Path, label: str) -> object:
    try:
        return json.loads(_read_text(path, label))
    except json.JSONDecodeError as exc:
        raise DiffInputError(f"{label} is not valid JSON: {exc}") from exc


def load_run_artifacts(run_dir: Path) -> RunArtifacts:
    if not run_dir.is_dir():
        raise DiffInputError(f"run directory does not exist: {run_dir}")

    openapi_path = run_dir / "openapi.yaml"
    provenance_path = run_dir / "provenance.json"
    validation_path = run_dir / "validation" / "report.json"
    manifest_path = run_dir / "manifest.json"
    integration_path = run_dir / "integration-contract.json"

    for path, label in (
        (openapi_path, "openapi.yaml"),
        (provenance_path, "provenance.json"),
        (validation_path, "validation/report.json"),
        (manifest_path, "manifest.json"),
    ):
        _require_file(path, label)

    try:
        openapi = yaml.safe_load(_read_text(openapi_path, "openapi.yaml"))
    except yaml.YAMLError as exc:
        raise DiffInputError(f"openapi.yaml is not valid YAML: {exc}") from exc
    if not isinstance(openapi, dict):
        raise DiffInputError("openapi.yaml must parse to an object")

    try:
        provenance = ProvenanceDocument.model_validate_json(
            _read_text(provenance_path, "provenance.json")
        )
        validation = ValidationReport.model_validate_json(
            _read_text(validation_path, "validation/report.json")
        )
        manifest = Manifest.model_validate_json(_read_text(manifest_path, "manifest.json"))
    except ValidationError as exc:
        raise DiffInputError(f"run artifact schema mismatch: {str(exc)[:200]}") from exc

    integration: dict | None = None
    if integration_path.exists():
        loaded = _load_json(integration_path, "integration-contract.json")
        if not isinstance(loaded, dict):
            raise DiffInputError("integration-contract.json must be an object")
        integration = loaded

    return RunArtifacts(
        run_dir=run_dir,
        openapi=openapi,
        integration=integration,
        provenance=provenance,
        validation=validation,
        manifest=manifest,
    )
```

- [ ] **Step 5: Add package exports**

Create `loop_apidoc/diff/__init__.py`:

```python
"""Run-to-run diff support for generated loop-apidoc artifacts."""

from loop_apidoc.diff.compare import build_diff_report
from loop_apidoc.diff.loader import DiffInputError, RunArtifacts, load_run_artifacts
from loop_apidoc.diff.models import DiffFinding, DiffImpact, DiffReport
from loop_apidoc.diff.report import render_markdown, write_reports

__all__ = [
    "DiffFinding",
    "DiffImpact",
    "DiffInputError",
    "DiffReport",
    "RunArtifacts",
    "build_diff_report",
    "load_run_artifacts",
    "render_markdown",
    "write_reports",
]
```

This import will fail until Tasks 2 and 3 create `compare.py` and `report.py`. To keep Task 1 tests focused, add temporary empty modules now:

Create `loop_apidoc/diff/compare.py`:

```python
from __future__ import annotations

from loop_apidoc.diff.loader import RunArtifacts
from loop_apidoc.diff.models import DiffReport


def build_diff_report(base: RunArtifacts, head: RunArtifacts) -> DiffReport:
    return DiffReport(
        base_run=str(base.run_dir),
        head_run=str(head.run_dir),
        summary={"breaking": 0, "additive": 0, "changed": 0, "source_only": 0},
        findings=[],
    )
```

Create `loop_apidoc/diff/report.py`:

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.diff.models import DiffReport


def render_markdown(report: DiffReport) -> str:
    return f"# Version Diff Report\n\nBase: {report.base_run}\nHead: {report.head_run}\n"


def write_reports(report: DiffReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
```

- [ ] **Step 6: Run loader tests and verify they pass**

Run: `uv run pytest tests/diff/test_loader.py -v`

Expected: PASS, all loader tests pass.

- [ ] **Step 7: Commit Task 1**

Run:

```bash
git add loop_apidoc/diff tests/diff/test_loader.py
git commit -m "Enable loading generated runs for diffing" \
  -m "Constraint: Diff inputs are generated run directories and must fail before writing outputs when required artifacts are invalid." \
  -m "Rejected: Reusing validate_run_dir for loading | validation reports compare existing output confidence, while loader needs raw artifact access." \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: Keep loader side-effect free; output creation belongs to the CLI/report writer." \
  -m "Tested: uv run pytest tests/diff/test_loader.py -v" \
  -m "Not-tested: Full suite not run for this loader-only commit."
```

## Task 2: OpenAPI Contract Impact Comparison

**Files:**
- Modify: `loop_apidoc/diff/compare.py`
- Create: `tests/diff/test_compare_openapi.py`

- [ ] **Step 1: Write failing OpenAPI comparison tests**

Create `tests/diff/test_compare_openapi.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.diff.compare import build_diff_report
from loop_apidoc.diff.loader import RunArtifacts
from loop_apidoc.diff.models import DiffImpact
from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.validate.models import ValidationReport

_NOW = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


def _doc() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/payments": {
                "post": {
                    "summary": "Create payment",
                    "parameters": [
                        {
                            "name": "merchant_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["amount"],
                                    "properties": {
                                        "amount": {"type": "integer"},
                                        "note": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"id": {"type": "string"}},
                                    }
                                }
                            },
                        },
                        "400": {"description": "bad request"},
                    },
                    "security": [{"ApiKeyAuth": []}],
                }
            }
        },
        "components": {
            "schemas": {
                "Payment": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string"}},
                }
            },
            "securitySchemes": {
                "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
            },
        },
    }


def _artifacts(openapi: dict, name: str = "run") -> RunArtifacts:
    return RunArtifacts(
        run_dir=Path(name),
        openapi=openapi,
        integration=None,
        provenance=ProvenanceDocument(notebook_url="", entries=[]),
        validation=ValidationReport(),
        manifest=Manifest(sources_root="./sources", generated_at=_NOW),
    )


def _findings(base: dict, head: dict):
    return build_diff_report(_artifacts(base, "base"), _artifacts(head, "head")).findings


def _by_summary(base: dict, head: dict, text: str):
    return [f for f in _findings(base, head) if text in f.summary]


def test_endpoint_addition_is_additive():
    base = _doc()
    head = _doc()
    head["paths"]["/refunds"] = {"post": {"responses": {"200": {"description": "ok"}}}}

    finding = _by_summary(base, head, "operation added")[0]
    assert finding.impact is DiffImpact.ADDITIVE
    assert finding.location == "POST /refunds"


def test_endpoint_removal_is_breaking():
    base = _doc()
    head = _doc()
    del head["paths"]["/payments"]

    finding = _by_summary(base, head, "operation removed")[0]
    assert finding.impact is DiffImpact.BREAKING
    assert finding.location == "POST /payments"


def test_required_parameter_addition_is_breaking():
    base = _doc()
    head = _doc()
    head["paths"]["/payments"]["post"]["parameters"].append(
        {
            "name": "signature",
            "in": "header",
            "required": True,
            "schema": {"type": "string"},
        }
    )

    finding = _by_summary(base, head, "required parameter added")[0]
    assert finding.impact is DiffImpact.BREAKING
    assert finding.location == "POST /payments parameters.header.signature"


def test_optional_parameter_addition_is_additive():
    base = _doc()
    head = _doc()
    head["paths"]["/payments"]["post"]["parameters"].append(
        {"name": "locale", "in": "query", "schema": {"type": "string"}}
    )

    finding = _by_summary(base, head, "optional parameter added")[0]
    assert finding.impact is DiffImpact.ADDITIVE
    assert finding.location == "POST /payments parameters.query.locale"


def test_parameter_type_change_is_breaking():
    base = _doc()
    head = _doc()
    head["paths"]["/payments"]["post"]["parameters"][0]["schema"] = {"type": "integer"}

    finding = _by_summary(base, head, "parameter schema changed")[0]
    assert finding.impact is DiffImpact.BREAKING


def test_required_request_property_addition_is_breaking():
    base = _doc()
    head = _doc()
    schema = head["paths"]["/payments"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    schema["required"].append("currency")
    schema["properties"]["currency"] = {"type": "string"}

    finding = _by_summary(base, head, "required property added")[0]
    assert finding.impact is DiffImpact.BREAKING
    assert finding.location == "POST /payments requestBody.application/json.currency"


def test_optional_request_property_addition_is_additive():
    base = _doc()
    head = _doc()
    schema = head["paths"]["/payments"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    schema["properties"]["channel"] = {"type": "string"}

    finding = _by_summary(base, head, "optional property added")[0]
    assert finding.impact is DiffImpact.ADDITIVE


def test_response_status_removal_is_breaking():
    base = _doc()
    head = _doc()
    del head["paths"]["/payments"]["post"]["responses"]["400"]

    finding = _by_summary(base, head, "response removed")[0]
    assert finding.impact is DiffImpact.BREAKING
    assert finding.location == "POST /payments responses.400"


def test_response_status_addition_is_additive():
    base = _doc()
    head = _doc()
    head["paths"]["/payments"]["post"]["responses"]["409"] = {"description": "conflict"}

    finding = _by_summary(base, head, "response added")[0]
    assert finding.impact is DiffImpact.ADDITIVE


def test_response_schema_type_change_is_breaking():
    base = _doc()
    head = _doc()
    head_schema = head["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    head_schema["properties"]["id"] = {"type": "integer"}

    finding = _by_summary(base, head, "schema changed")[0]
    assert finding.impact is DiffImpact.BREAKING
    assert "responses.200.application/json.id" in finding.location


def test_info_and_server_changes_are_changed():
    base = _doc()
    head = _doc()
    head["info"]["version"] = "1.1.0"
    head["servers"] = [{"url": "https://sandbox.example.com"}]

    findings = _findings(base, head)
    changed = [f for f in findings if f.impact is DiffImpact.CHANGED]
    assert any(f.location == "openapi.info.version" for f in changed)
    assert any(f.location == "openapi.servers" for f in changed)


def test_security_scheme_change_is_breaking():
    base = _doc()
    head = _doc()
    head["components"]["securitySchemes"]["ApiKeyAuth"]["name"] = "Authorization"

    finding = _by_summary(base, head, "security scheme changed")[0]
    assert finding.impact is DiffImpact.BREAKING


def test_summary_counts_all_impacts():
    base = _doc()
    head = _doc()
    head["info"]["version"] = "1.1.0"
    head["paths"]["/refunds"] = {"post": {"responses": {"200": {"description": "ok"}}}}
    del head["paths"]["/payments"]["post"]["responses"]["400"]

    report = build_diff_report(_artifacts(base, "base"), _artifacts(head, "head"))

    assert report.summary["breaking"] == 1
    assert report.summary["additive"] == 1
    assert report.summary["changed"] == 1
    assert report.summary["source_only"] == 0
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/diff/test_compare_openapi.py -v`

Expected: FAIL because `compare.py` still returns an empty report.

- [ ] **Step 3: Replace `compare.py` with OpenAPI comparison implementation**

Replace `loop_apidoc/diff/compare.py` with:

```python
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from loop_apidoc.diff.loader import RunArtifacts
from loop_apidoc.diff.models import DiffFinding, DiffImpact, DiffReport

_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
_IMPACT_ORDER = {
    DiffImpact.BREAKING: 0,
    DiffImpact.ADDITIVE: 1,
    DiffImpact.CHANGED: 2,
    DiffImpact.SOURCE_ONLY: 3,
}
_SUMMARY_KEYS = [impact.value for impact in DiffImpact]


def _finding(
    impact: DiffImpact,
    area: str,
    location: str,
    summary: str,
    before: Any | None = None,
    after: Any | None = None,
) -> DiffFinding:
    return DiffFinding(
        impact=impact,
        area=area,
        location=location,
        summary=summary,
        before=before,
        after=after,
    )


def _sorted_findings(findings: Iterable[DiffFinding]) -> list[DiffFinding]:
    return sorted(
        findings,
        key=lambda f: (_IMPACT_ORDER[f.impact], f.area, f.location, f.summary),
    )


def _summary(findings: list[DiffFinding]) -> dict[str, int]:
    counts = {key: 0 for key in _SUMMARY_KEYS}
    for finding in findings:
        counts[finding.impact.value] += 1
    return counts


def _operation_map(openapi: dict) -> dict[str, dict]:
    paths = openapi.get("paths")
    if not isinstance(paths, dict):
        return {}
    out: dict[str, dict] = {}
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            method_l = str(method).lower()
            if method_l in _METHODS and isinstance(operation, dict):
                out[f"{method_l.upper()} {path}"] = operation
    return out


def _schema_signature(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    keys = ("type", "$ref", "enum", "oneOf", "anyOf", "allOf", "format")
    return {key: schema.get(key) for key in keys if key in schema}


def _content_schemas(container: dict | None) -> dict[str, dict]:
    if not isinstance(container, dict):
        return {}
    content = container.get("content")
    if not isinstance(content, dict):
        return {}
    out: dict[str, dict] = {}
    for media_type, media in content.items():
        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
            out[str(media_type)] = media["schema"]
    return out


def _request_schemas(operation: dict) -> dict[str, dict]:
    return _content_schemas(operation.get("requestBody"))


def _response_schemas(response: dict) -> dict[str, dict]:
    return _content_schemas(response)


def _properties(schema: dict) -> dict[str, dict]:
    props = schema.get("properties")
    return props if isinstance(props, dict) else {}


def _required(schema: dict) -> set[str]:
    raw = schema.get("required")
    return {str(item) for item in raw} if isinstance(raw, list) else set()


def _compare_schema(
    base: dict,
    head: dict,
    *,
    area: str,
    location: str,
    findings: list[DiffFinding],
    added_required_is_breaking: bool,
    removed_property_is_breaking: bool,
) -> None:
    base_sig = _schema_signature(base)
    head_sig = _schema_signature(head)
    if base_sig != head_sig:
        findings.append(
            _finding(
                DiffImpact.BREAKING,
                area,
                location,
                "schema changed",
                base_sig,
                head_sig,
            )
        )

    base_props = _properties(base)
    head_props = _properties(head)
    base_required = _required(base)
    head_required = _required(head)

    for name in sorted(head_props.keys() - base_props.keys()):
        is_required = name in head_required
        if is_required and added_required_is_breaking:
            impact = DiffImpact.BREAKING
            summary = "required property added"
        else:
            impact = DiffImpact.ADDITIVE
            summary = "optional property added"
        findings.append(
            _finding(impact, area, f"{location}.{name}", summary, None, head_props[name])
        )

    for name in sorted(base_props.keys() - head_props.keys()):
        impact = DiffImpact.BREAKING if removed_property_is_breaking else DiffImpact.CHANGED
        findings.append(
            _finding(impact, area, f"{location}.{name}", "property removed", base_props[name], None)
        )

    for name in sorted(base_props.keys() & head_props.keys()):
        _compare_schema(
            base_props[name],
            head_props[name],
            area=area,
            location=f"{location}.{name}",
            findings=findings,
            added_required_is_breaking=added_required_is_breaking,
            removed_property_is_breaking=removed_property_is_breaking,
        )

    for name in sorted(head_required - base_required):
        if name in base_props and name in head_props:
            findings.append(
                _finding(
                    DiffImpact.BREAKING,
                    area,
                    f"{location}.{name}",
                    "property became required",
                    sorted(base_required),
                    sorted(head_required),
                )
            )

    for name in sorted(base_required - head_required):
        findings.append(
            _finding(
                DiffImpact.CHANGED,
                area,
                f"{location}.{name}",
                "property no longer required",
                sorted(base_required),
                sorted(head_required),
            )
        )


def _parameter_key(parameter: dict) -> str:
    return f"{parameter.get('in', 'query')}.{parameter.get('name', '')}"


def _parameter_map(operation: dict) -> dict[str, dict]:
    params = operation.get("parameters")
    if not isinstance(params, list):
        return {}
    return {
        _parameter_key(param): param
        for param in params
        if isinstance(param, dict) and param.get("name")
    }


def _compare_parameters(
    op_key: str,
    base: dict,
    head: dict,
    findings: list[DiffFinding],
) -> None:
    base_params = _parameter_map(base)
    head_params = _parameter_map(head)
    for key in sorted(head_params.keys() - base_params.keys()):
        param = head_params[key]
        required = bool(param.get("required"))
        findings.append(
            _finding(
                DiffImpact.BREAKING if required else DiffImpact.ADDITIVE,
                "openapi.parameters",
                f"{op_key} parameters.{key}",
                "required parameter added" if required else "optional parameter added",
                None,
                param,
            )
        )
    for key in sorted(base_params.keys() - head_params.keys()):
        findings.append(
            _finding(
                DiffImpact.CHANGED,
                "openapi.parameters",
                f"{op_key} parameters.{key}",
                "parameter removed",
                base_params[key],
                None,
            )
        )
    for key in sorted(base_params.keys() & head_params.keys()):
        before = _schema_signature(base_params[key].get("schema"))
        after = _schema_signature(head_params[key].get("schema"))
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


def _compare_request_body(
    op_key: str,
    base: dict,
    head: dict,
    findings: list[DiffFinding],
) -> None:
    base_schemas = _request_schemas(base)
    head_schemas = _request_schemas(head)
    for media_type in sorted(head_schemas.keys() - base_schemas.keys()):
        findings.append(
            _finding(
                DiffImpact.ADDITIVE,
                "openapi.requestBody",
                f"{op_key} requestBody.{media_type}",
                "request media type added",
                None,
                head_schemas[media_type],
            )
        )
    for media_type in sorted(base_schemas.keys() - head_schemas.keys()):
        findings.append(
            _finding(
                DiffImpact.BREAKING,
                "openapi.requestBody",
                f"{op_key} requestBody.{media_type}",
                "request media type removed",
                base_schemas[media_type],
                None,
            )
        )
    for media_type in sorted(base_schemas.keys() & head_schemas.keys()):
        _compare_schema(
            base_schemas[media_type],
            head_schemas[media_type],
            area="openapi.requestBody",
            location=f"{op_key} requestBody.{media_type}",
            findings=findings,
            added_required_is_breaking=True,
            removed_property_is_breaking=False,
        )


def _responses(operation: dict) -> dict[str, dict]:
    responses = operation.get("responses")
    return responses if isinstance(responses, dict) else {}


def _compare_responses(
    op_key: str,
    base: dict,
    head: dict,
    findings: list[DiffFinding],
) -> None:
    base_responses = _responses(base)
    head_responses = _responses(head)
    for status in sorted(head_responses.keys() - base_responses.keys()):
        findings.append(
            _finding(
                DiffImpact.ADDITIVE,
                "openapi.responses",
                f"{op_key} responses.{status}",
                "response added",
                None,
                head_responses[status],
            )
        )
    for status in sorted(base_responses.keys() - head_responses.keys()):
        findings.append(
            _finding(
                DiffImpact.BREAKING,
                "openapi.responses",
                f"{op_key} responses.{status}",
                "response removed",
                base_responses[status],
                None,
            )
        )
    for status in sorted(base_responses.keys() & head_responses.keys()):
        base_schemas = _response_schemas(base_responses[status])
        head_schemas = _response_schemas(head_responses[status])
        for media_type in sorted(head_schemas.keys() - base_schemas.keys()):
            findings.append(
                _finding(
                    DiffImpact.ADDITIVE,
                    "openapi.responses",
                    f"{op_key} responses.{status}.{media_type}",
                    "response media type added",
                    None,
                    head_schemas[media_type],
                )
            )
        for media_type in sorted(base_schemas.keys() - head_schemas.keys()):
            findings.append(
                _finding(
                    DiffImpact.BREAKING,
                    "openapi.responses",
                    f"{op_key} responses.{status}.{media_type}",
                    "response media type removed",
                    base_schemas[media_type],
                    None,
                )
            )
        for media_type in sorted(base_schemas.keys() & head_schemas.keys()):
            _compare_schema(
                base_schemas[media_type],
                head_schemas[media_type],
                area="openapi.responses",
                location=f"{op_key} responses.{status}.{media_type}",
                findings=findings,
                added_required_is_breaking=False,
                removed_property_is_breaking=True,
            )


def _compare_operations(base: dict, head: dict) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_ops = _operation_map(base)
    head_ops = _operation_map(head)
    for op_key in sorted(head_ops.keys() - base_ops.keys()):
        findings.append(
            _finding(DiffImpact.ADDITIVE, "openapi.paths", op_key, "operation added", None, head_ops[op_key])
        )
    for op_key in sorted(base_ops.keys() - head_ops.keys()):
        findings.append(
            _finding(DiffImpact.BREAKING, "openapi.paths", op_key, "operation removed", base_ops[op_key], None)
        )
    for op_key in sorted(base_ops.keys() & head_ops.keys()):
        base_op = base_ops[op_key]
        head_op = head_ops[op_key]
        for field in ("summary", "description"):
            if base_op.get(field) != head_op.get(field):
                findings.append(
                    _finding(
                        DiffImpact.CHANGED,
                        "openapi.operations",
                        f"{op_key}.{field}",
                        f"operation {field} changed",
                        base_op.get(field),
                        head_op.get(field),
                    )
                )
        if base_op.get("security") != head_op.get("security"):
            findings.append(
                _finding(
                    DiffImpact.BREAKING,
                    "openapi.security",
                    f"{op_key}.security",
                    "operation security changed",
                    base_op.get("security"),
                    head_op.get("security"),
                )
            )
        _compare_parameters(op_key, base_op, head_op, findings)
        _compare_request_body(op_key, base_op, head_op, findings)
        _compare_responses(op_key, base_op, head_op, findings)
    return findings


def _components(openapi: dict, name: str) -> dict:
    components = openapi.get("components")
    if not isinstance(components, dict):
        return {}
    section = components.get(name)
    return section if isinstance(section, dict) else {}


def _compare_component_schemas(base: dict, head: dict) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_schemas = _components(base, "schemas")
    head_schemas = _components(head, "schemas")
    for name in sorted(head_schemas.keys() - base_schemas.keys()):
        findings.append(
            _finding(DiffImpact.ADDITIVE, "openapi.schemas", f"components.schemas.{name}", "schema added", None, head_schemas[name])
        )
    for name in sorted(base_schemas.keys() - head_schemas.keys()):
        findings.append(
            _finding(DiffImpact.CHANGED, "openapi.schemas", f"components.schemas.{name}", "schema removed", base_schemas[name], None)
        )
    for name in sorted(base_schemas.keys() & head_schemas.keys()):
        if isinstance(base_schemas[name], dict) and isinstance(head_schemas[name], dict):
            _compare_schema(
                base_schemas[name],
                head_schemas[name],
                area="openapi.schemas",
                location=f"components.schemas.{name}",
                findings=findings,
                added_required_is_breaking=True,
                removed_property_is_breaking=True,
            )
        elif base_schemas[name] != head_schemas[name]:
            findings.append(
                _finding(DiffImpact.BREAKING, "openapi.schemas", f"components.schemas.{name}", "schema changed", base_schemas[name], head_schemas[name])
            )
    return findings


def _compare_security_schemes(base: dict, head: dict) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_schemes = _components(base, "securitySchemes")
    head_schemes = _components(head, "securitySchemes")
    for name in sorted(head_schemes.keys() - base_schemes.keys()):
        findings.append(
            _finding(DiffImpact.ADDITIVE, "openapi.security", f"components.securitySchemes.{name}", "security scheme added", None, head_schemes[name])
        )
    for name in sorted(base_schemes.keys() - head_schemes.keys()):
        findings.append(
            _finding(DiffImpact.BREAKING, "openapi.security", f"components.securitySchemes.{name}", "security scheme removed", base_schemes[name], None)
        )
    for name in sorted(base_schemes.keys() & head_schemes.keys()):
        if base_schemes[name] != head_schemes[name]:
            findings.append(
                _finding(DiffImpact.BREAKING, "openapi.security", f"components.securitySchemes.{name}", "security scheme changed", base_schemes[name], head_schemes[name])
            )
    return findings


def _compare_openapi(base: dict, head: dict) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    for field in ("title", "version"):
        before = base.get("info", {}).get(field) if isinstance(base.get("info"), dict) else None
        after = head.get("info", {}).get(field) if isinstance(head.get("info"), dict) else None
        if before != after:
            findings.append(
                _finding(DiffImpact.CHANGED, "openapi.info", f"openapi.info.{field}", f"info {field} changed", before, after)
            )
    if base.get("servers") != head.get("servers"):
        findings.append(
            _finding(DiffImpact.CHANGED, "openapi.servers", "openapi.servers", "servers changed", base.get("servers"), head.get("servers"))
        )
    findings.extend(_compare_operations(base, head))
    findings.extend(_compare_component_schemas(base, head))
    findings.extend(_compare_security_schemes(base, head))
    return findings


def build_diff_report(base: RunArtifacts, head: RunArtifacts) -> DiffReport:
    findings = _sorted_findings(_compare_openapi(base.openapi, head.openapi))
    return DiffReport(
        base_run=str(base.run_dir),
        head_run=str(head.run_dir),
        summary=_summary(findings),
        findings=findings,
    )
```

- [ ] **Step 4: Run OpenAPI comparison tests**

Run: `uv run pytest tests/diff/test_compare_openapi.py -v`

Expected: PASS.

- [ ] **Step 5: Run loader regression tests**

Run: `uv run pytest tests/diff/test_loader.py tests/diff/test_compare_openapi.py -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add loop_apidoc/diff/compare.py tests/diff/test_compare_openapi.py
git commit -m "Classify OpenAPI run diffs by impact" \
  -m "Constraint: First diff surface must report downstream contract impact, not raw YAML text changes." \
  -m "Rejected: Treating every OpenAPI value change as breaking | descriptions, servers, and metadata require a lower changed impact." \
  -m "Confidence: medium" \
  -m "Scope-risk: moderate" \
  -m "Directive: Keep comparison deterministic and stable-sorted before adding more artifact surfaces." \
  -m "Tested: uv run pytest tests/diff/test_loader.py tests/diff/test_compare_openapi.py -v" \
  -m "Not-tested: CLI command not wired yet."
```

## Task 3: Integration, Provenance, Validation, Manifest, And Report Rendering

**Files:**
- Modify: `loop_apidoc/diff/compare.py`
- Modify: `loop_apidoc/diff/report.py`
- Create: `tests/diff/test_compare_supporting_artifacts.py`
- Create: `tests/diff/test_report.py`

- [ ] **Step 1: Write supporting artifact comparison tests**

Create `tests/diff/test_compare_supporting_artifacts.py`:

```python
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.diff.compare import build_diff_report
from loop_apidoc.diff.loader import RunArtifacts
from loop_apidoc.diff.models import DiffImpact
from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport

_NOW = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "paths": {},
    }


def _manifest(sha256: str = "abc") -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=10,
                sha256=sha256,
                scanned_at=_NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )


def _artifacts(**overrides) -> RunArtifacts:
    base = RunArtifacts(
        run_dir=Path(overrides.pop("run_name", "run")),
        openapi=_openapi(),
        integration=None,
        provenance=ProvenanceDocument(notebook_url="", entries=[]),
        validation=ValidationReport(),
        manifest=_manifest(),
    )
    return replace(base, **overrides)


def _find(text: str, findings):
    return [finding for finding in findings if text in finding.summary][0]


def test_integration_crypto_algorithm_change_is_breaking():
    base = _artifacts(
        integration={"crypto": [{"name": "TradeInfo", "algorithm": "AES-256-CBC"}]}
    )
    head = _artifacts(
        integration={"crypto": [{"name": "TradeInfo", "algorithm": "AES-256-GCM"}]}
    )

    report = build_diff_report(base, head)
    finding = _find("integration crypto core field changed", report.findings)

    assert finding.impact is DiffImpact.BREAKING
    assert finding.location == "integration.crypto.TradeInfo.algorithm"


def test_integration_callback_detail_change_is_changed():
    base = _artifacts(
        integration={"callbacks": [{"name": "notify", "transport": "POST"}]}
    )
    head = _artifacts(
        integration={"callbacks": [{"name": "notify", "transport": "HTTPS POST"}]}
    )

    report = build_diff_report(base, head)
    finding = _find("integration callback field changed", report.findings)

    assert finding.impact is DiffImpact.CHANGED
    assert finding.location == "integration.callbacks.notify.transport"


def test_integration_item_added_is_additive_and_removed_is_breaking():
    base = _artifacts(integration={"crypto": [{"name": "sig"}]})
    head = _artifacts(integration={"crypto": [{"name": "sig"}, {"name": "encrypt"}]})
    added = _find("integration crypto added", build_diff_report(base, head).findings)
    removed = _find("integration crypto removed", build_diff_report(head, base).findings)

    assert added.impact is DiffImpact.ADDITIVE
    assert removed.impact is DiffImpact.BREAKING


def test_provenance_citation_change_is_source_only():
    base = _artifacts(
        provenance=ProvenanceDocument(
            notebook_url="",
            entries=[
                ProvenanceEntry(
                    target="paths./payments.post",
                    status=PlanItemStatus.SUPPORTED,
                    manifest_source="manual-v1.md",
                    query_id="06",
                )
            ],
        )
    )
    head = _artifacts(
        provenance=ProvenanceDocument(
            notebook_url="",
            entries=[
                ProvenanceEntry(
                    target="paths./payments.post",
                    status=PlanItemStatus.SUPPORTED,
                    manifest_source="manual-v2.md",
                    query_id="06",
                )
            ],
        )
    )

    finding = _find("provenance changed", build_diff_report(base, head).findings)
    assert finding.impact is DiffImpact.SOURCE_ONLY


def test_validation_issue_change_is_source_only():
    base = _artifacts(validation=ValidationReport())
    head = _artifacts(
        validation=ValidationReport(
            issues=[
                Issue(
                    code=IssueCode.REQUIRED_INFO_MISSING,
                    severity=Severity.WARNING,
                    location="operational",
                    evidence="no rate limit",
                    suggested_fix="add source",
                )
            ]
        )
    )

    finding = _find("validation issue added", build_diff_report(base, head).findings)
    assert finding.impact is DiffImpact.SOURCE_ONLY


def test_manifest_source_hash_change_is_source_only():
    base = _artifacts(manifest=_manifest("abc"))
    head = _artifacts(manifest=_manifest("def"))

    finding = _find("manifest source changed", build_diff_report(base, head).findings)
    assert finding.impact is DiffImpact.SOURCE_ONLY
    assert finding.location == "manifest.local.manual.md"
```

- [ ] **Step 2: Write report rendering tests**

Create `tests/diff/test_report.py`:

```python
from __future__ import annotations

from loop_apidoc.diff.models import DiffFinding, DiffImpact, DiffReport
from loop_apidoc.diff.report import render_markdown, write_reports


def _report() -> DiffReport:
    return DiffReport(
        base_run="output/base",
        head_run="output/head",
        summary={"breaking": 1, "additive": 1, "changed": 0, "source_only": 1},
        findings=[
            DiffFinding(
                impact=DiffImpact.BREAKING,
                area="openapi.responses",
                location="POST /payments responses.400",
                summary="response removed",
                before={"description": "bad"},
            ),
            DiffFinding(
                impact=DiffImpact.ADDITIVE,
                area="openapi.paths",
                location="POST /refunds",
                summary="operation added",
                after={"responses": {"200": {"description": "ok"}}},
            ),
            DiffFinding(
                impact=DiffImpact.SOURCE_ONLY,
                area="provenance",
                location="paths./payments.post",
                summary="provenance changed",
            ),
        ],
    )


def test_render_markdown_groups_by_impact_and_includes_counts():
    md = render_markdown(_report())

    assert "# Version Diff Report" in md
    assert "Base: `output/base`" in md
    assert "| breaking | 1 |" in md
    assert "## Breaking" in md
    assert "`POST /payments responses.400`: response removed" in md
    assert "## Additive" in md
    assert "## Source Only" in md


def test_write_reports_emits_json_and_markdown(tmp_path):
    out = tmp_path / "diff"
    write_reports(_report(), out)

    loaded = DiffReport.model_validate_json((out / "report.json").read_text())
    assert loaded == _report()
    assert "Version Diff Report" in (out / "report.md").read_text(encoding="utf-8")
```

- [ ] **Step 3: Run tests and verify they fail**

Run: `uv run pytest tests/diff/test_compare_supporting_artifacts.py tests/diff/test_report.py -v`

Expected: FAIL because supporting artifact comparison and full report rendering are not implemented yet.

- [ ] **Step 4: Extend `compare.py` for supporting artifacts**

Append these helper functions above `build_diff_report` in `loop_apidoc/diff/compare.py`:

```python
def _integration_items(integration: dict | None, section: str) -> dict[str, dict]:
    if not integration:
        return {}
    raw = integration.get(section)
    if not isinstance(raw, list):
        return {}
    out: dict[str, dict] = {}
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        if section == "crypto":
            key = item.get("name") or f"{item.get('purpose', 'crypto')}:{item.get('algorithm', idx)}"
        elif section == "callbacks":
            key = item.get("name") or item.get("trigger") or str(idx)
        elif section == "field_conditions":
            key = f"{item.get('scope', idx)}:{item.get('when', '')}"
        elif section == "test_cases":
            key = item.get("name") or item.get("operation_ref") or str(idx)
        else:
            key = str(idx)
        out[str(key)] = item
    return out


def _compare_section_items(
    base: dict | None,
    head: dict | None,
    section: str,
    singular: str,
    core_fields: set[str],
) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_items = _integration_items(base, section)
    head_items = _integration_items(head, section)
    for key in sorted(head_items.keys() - base_items.keys()):
        findings.append(
            _finding(
                DiffImpact.ADDITIVE,
                "integration",
                f"integration.{section}.{key}",
                f"integration {singular} added",
                None,
                head_items[key],
            )
        )
    for key in sorted(base_items.keys() - head_items.keys()):
        findings.append(
            _finding(
                DiffImpact.BREAKING,
                "integration",
                f"integration.{section}.{key}",
                f"integration {singular} removed",
                base_items[key],
                None,
            )
        )
    for key in sorted(base_items.keys() & head_items.keys()):
        fields = sorted(set(base_items[key]) | set(head_items[key]))
        for field in fields:
            before = base_items[key].get(field)
            after = head_items[key].get(field)
            if before == after:
                continue
            impact = DiffImpact.BREAKING if field in core_fields else DiffImpact.CHANGED
            core = " core" if impact is DiffImpact.BREAKING else ""
            findings.append(
                _finding(
                    impact,
                    "integration",
                    f"integration.{section}.{key}.{field}",
                    f"integration {singular}{core} field changed",
                    before,
                    after,
                )
            )
    return findings


def _compare_integration(base: dict | None, head: dict | None) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    findings.extend(
        _compare_section_items(
            base,
            head,
            "crypto",
            "crypto",
            {"algorithm", "mode", "key_source", "payload_assembly", "verify"},
        )
    )
    findings.extend(
        _compare_section_items(
            base,
            head,
            "callbacks",
            "callback",
            {"verification", "expected_response"},
        )
    )
    findings.extend(
        _compare_section_items(
            base,
            head,
            "field_conditions",
            "field condition",
            {"then_required"},
        )
    )
    findings.extend(
        _compare_section_items(
            base,
            head,
            "test_cases",
            "test case",
            set(),
        )
    )
    return findings


def _provenance_map(artifacts: RunArtifacts) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for entry in artifacts.provenance.entries:
        out.setdefault(entry.target, []).append(entry.model_dump(mode="json"))
    return out


def _compare_provenance(base: RunArtifacts, head: RunArtifacts) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_entries = _provenance_map(base)
    head_entries = _provenance_map(head)
    for target in sorted(set(base_entries) | set(head_entries)):
        before = base_entries.get(target)
        after = head_entries.get(target)
        if before != after:
            findings.append(
                _finding(
                    DiffImpact.SOURCE_ONLY,
                    "provenance",
                    target,
                    "provenance changed",
                    before,
                    after,
                )
            )
    return findings


def _issue_key(issue) -> tuple[str, str, str, str]:
    return (
        issue.code.value,
        issue.severity.value,
        issue.location,
        issue.evidence,
    )


def _compare_validation(base: RunArtifacts, head: RunArtifacts) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_issues = {_issue_key(issue): issue for issue in base.validation.issues}
    head_issues = {_issue_key(issue): issue for issue in head.validation.issues}
    for key in sorted(head_issues.keys() - base_issues.keys()):
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "validation",
                f"validation.{key[0]}.{key[2]}",
                "validation issue added",
                None,
                head_issues[key].model_dump(mode="json"),
            )
        )
    for key in sorted(base_issues.keys() - head_issues.keys()):
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "validation",
                f"validation.{key[0]}.{key[2]}",
                "validation issue removed",
                base_issues[key].model_dump(mode="json"),
                None,
            )
        )
    return findings


def _manifest_local_map(artifacts: RunArtifacts) -> dict[str, dict]:
    return {
        source.relative_path: source.model_dump(mode="json")
        for source in artifacts.manifest.local_sources
    }


def _manifest_url_map(artifacts: RunArtifacts) -> dict[str, dict]:
    return {source.url: source.model_dump(mode="json") for source in artifacts.manifest.url_sources}


def _compare_manifest(base: RunArtifacts, head: RunArtifacts) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    for label, base_map, head_map in (
        ("local", _manifest_local_map(base), _manifest_local_map(head)),
        ("url", _manifest_url_map(base), _manifest_url_map(head)),
    ):
        for key in sorted(set(base_map) | set(head_map)):
            before = base_map.get(key)
            after = head_map.get(key)
            if before != after:
                findings.append(
                    _finding(
                        DiffImpact.SOURCE_ONLY,
                        "manifest",
                        f"manifest.{label}.{key}",
                        "manifest source changed",
                        before,
                        after,
                    )
                )
    return findings
```

Then replace `build_diff_report` with:

```python
def build_diff_report(base: RunArtifacts, head: RunArtifacts) -> DiffReport:
    findings: list[DiffFinding] = []
    findings.extend(_compare_openapi(base.openapi, head.openapi))
    findings.extend(_compare_integration(base.integration, head.integration))
    findings.extend(_compare_provenance(base, head))
    findings.extend(_compare_validation(base, head))
    findings.extend(_compare_manifest(base, head))
    findings = _sorted_findings(findings)
    return DiffReport(
        base_run=str(base.run_dir),
        head_run=str(head.run_dir),
        summary=_summary(findings),
        findings=findings,
    )
```

- [ ] **Step 5: Replace `report.py` with full renderer**

Replace `loop_apidoc/diff/report.py` with:

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.diff.models import DiffImpact, DiffReport

_HEADINGS = {
    DiffImpact.BREAKING: "Breaking",
    DiffImpact.ADDITIVE: "Additive",
    DiffImpact.CHANGED: "Changed",
    DiffImpact.SOURCE_ONLY: "Source Only",
}


def render_markdown(report: DiffReport) -> str:
    lines = [
        "# Version Diff Report",
        "",
        f"Base: `{report.base_run}`",
        f"Head: `{report.head_run}`",
        "",
        "## Summary",
        "",
        "| Impact | Count |",
        "| --- | ---: |",
    ]
    for impact in DiffImpact:
        lines.append(f"| {impact.value} | {report.summary.get(impact.value, 0)} |")
    if not report.findings:
        lines.extend(["", "No differences found."])
        return "\n".join(lines) + "\n"

    for impact in DiffImpact:
        grouped = [finding for finding in report.findings if finding.impact is impact]
        if not grouped:
            continue
        lines.extend(["", f"## {_HEADINGS[impact]}", ""])
        for finding in grouped:
            lines.append(f"- `{finding.location}`: {finding.summary}")
    return "\n".join(lines) + "\n"


def write_reports(report: DiffReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
```

- [ ] **Step 6: Run supporting artifact and report tests**

Run: `uv run pytest tests/diff/test_compare_supporting_artifacts.py tests/diff/test_report.py -v`

Expected: PASS.

- [ ] **Step 7: Run all diff tests**

Run: `uv run pytest tests/diff -v`

Expected: PASS.

- [ ] **Step 8: Commit Task 3**

Run:

```bash
git add loop_apidoc/diff/compare.py loop_apidoc/diff/report.py tests/diff/test_compare_supporting_artifacts.py tests/diff/test_report.py
git commit -m "Compare integration and source confidence artifacts" \
  -m "Constraint: The first report must cover integration contracts and traceability without broadening into generated Markdown or examples." \
  -m "Rejected: Treating provenance and validation changes as contract changes | they affect confidence and traceability, not API shape." \
  -m "Confidence: medium" \
  -m "Scope-risk: moderate" \
  -m "Directive: Keep source-only findings separate from OpenAPI and integration-contract impact." \
  -m "Tested: uv run pytest tests/diff -v" \
  -m "Not-tested: Typer CLI path not wired yet."
```

## Task 4: CLI Command, README, And Smoke Tests

**Files:**
- Modify: `loop_apidoc/cli.py`
- Modify: `README.md`
- Create: `tests/test_cli_diff.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_diff.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.validate.models import ValidationReport

runner = CliRunner()
_NOW = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


def _openapi(path: str) -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "paths": {
            path: {
                "get": {
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }


def _write_run(run_dir: Path, path: str) -> Path:
    run_dir.mkdir(parents=True)
    (run_dir / "openapi.yaml").write_text(
        yaml.safe_dump(_openapi(path), sort_keys=False),
        encoding="utf-8",
    )
    (run_dir / "provenance.json").write_text(
        ProvenanceDocument(notebook_url="", entries=[]).model_dump_json(indent=2),
        encoding="utf-8",
    )
    (run_dir / "validation").mkdir()
    (run_dir / "validation" / "report.json").write_text(
        ValidationReport().model_dump_json(indent=2),
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        Manifest(sources_root="./sources", generated_at=_NOW).model_dump_json(indent=2),
        encoding="utf-8",
    )
    return run_dir


def test_diff_writes_default_reports_under_head_run(tmp_path):
    base = _write_run(tmp_path / "base", "/payments")
    head = _write_run(tmp_path / "head", "/payments")
    head_doc = yaml.safe_load((head / "openapi.yaml").read_text(encoding="utf-8"))
    head_doc["paths"]["/refunds"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    (head / "openapi.yaml").write_text(
        yaml.safe_dump(head_doc, sort_keys=False),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["diff", "--base", str(base), "--head", str(head)])

    assert result.exit_code == 0
    report_json = head / "diff" / "report.json"
    report_md = head / "diff" / "report.md"
    assert report_json.is_file()
    assert report_md.is_file()
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["summary"]["additive"] == 1
    assert "diff/report.json" in result.stdout


def test_diff_writes_output_override(tmp_path):
    base = _write_run(tmp_path / "base", "/payments")
    head = _write_run(tmp_path / "head", "/refunds")
    out = tmp_path / "custom-diff"

    result = runner.invoke(
        app,
        ["diff", "--base", str(base), "--head", str(head), "--output", str(out)],
    )

    assert result.exit_code == 0
    assert (out / "report.json").is_file()
    assert (out / "report.md").is_file()


def test_diff_invalid_input_exits_2_without_output_dir(tmp_path):
    base = _write_run(tmp_path / "base", "/payments")
    head = tmp_path / "missing"

    result = runner.invoke(app, ["diff", "--base", str(base), "--head", str(head)])

    assert result.exit_code == 2
    assert not (head / "diff").exists()
    assert "diff input error" in result.stderr


def test_diff_output_path_as_file_exits_2(tmp_path):
    base = _write_run(tmp_path / "base", "/payments")
    head = _write_run(tmp_path / "head", "/refunds")
    out = tmp_path / "report-file"
    out.write_text("not a directory", encoding="utf-8")

    result = runner.invoke(
        app,
        ["diff", "--base", str(base), "--head", str(head), "--output", str(out)],
    )

    assert result.exit_code == 2
    assert "output path is a file" in result.stderr
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run: `uv run pytest tests/test_cli_diff.py -v`

Expected: FAIL because the `diff` command is not registered.

- [ ] **Step 3: Add CLI command**

In `loop_apidoc/cli.py`, add this command below `validate` and above `assemble`:

```python
@app.command()
def diff(
    base: Path = typer.Option(
        ...,
        "--base",
        help="舊版/基準 run 目錄",
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    head: Path = typer.Option(
        ...,
        "--head",
        help="新版/待比較 run 目錄",
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="diff report 輸出目錄；省略時寫入 <head>/diff",
    ),
) -> None:
    """比較兩個已完成 run 目錄並輸出版本差異報告。"""
    from loop_apidoc.diff import (
        DiffInputError,
        build_diff_report,
        load_run_artifacts,
        write_reports,
    )

    output_dir = output or (head / "diff")
    if output_dir.exists() and output_dir.is_file():
        typer.echo(f"diff input error: output path is a file: {output_dir}", err=True)
        raise typer.Exit(code=2)

    try:
        base_artifacts = load_run_artifacts(base)
        head_artifacts = load_run_artifacts(head)
        report = build_diff_report(base_artifacts, head_artifacts)
    except DiffInputError as exc:
        typer.echo(f"diff input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    write_reports(report, output_dir)
    typer.echo(
        "diff COMPLETE: "
        f"breaking {report.summary['breaking']}，"
        f"additive {report.summary['additive']}，"
        f"changed {report.summary['changed']}，"
        f"source_only {report.summary['source_only']}；"
        f"報告寫入 {output_dir / 'report.json'}"
    )
```

- [ ] **Step 4: Update README usage**

In `README.md`, add this section after the `validate` command section and before `preprocess`:

````markdown
### `diff` — 比較兩次 run 的版本差異

```bash
uv run loop-apidoc diff --base ./output/<old-run> --head ./output/<new-run>
```

比較兩個已完成 run directory，依 downstream impact 輸出差異報告。預設寫入
`<new-run>/diff/report.{json,md}`；可用 `--output` 指定其他目錄。差異分類為
`breaking`、`additive`、`changed`、`source_only`，比較範圍包含
`openapi.yaml`、`integration-contract.json`、`provenance.json`、
`validation/report.json` 與 `manifest.json`。第一版不比較 Markdown guide 或
generated examples。
````

- [ ] **Step 5: Run CLI tests**

Run: `uv run pytest tests/test_cli_diff.py -v`

Expected: PASS.

- [ ] **Step 6: Run all diff and CLI tests**

Run: `uv run pytest tests/diff tests/test_cli_diff.py -v`

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

Run:

```bash
git add loop_apidoc/cli.py README.md tests/test_cli_diff.py
git commit -m "Expose run diff reports through the CLI" \
  -m "Constraint: CLI must load both inputs successfully before creating report output." \
  -m "Rejected: Non-zero exit for breaking findings | breaking changes are report content, not command failure." \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: Keep command wiring thin; comparison rules belong in loop_apidoc/diff." \
  -m "Tested: uv run pytest tests/diff tests/test_cli_diff.py -v" \
  -m "Not-tested: Full repository suite not run for this CLI-only commit."
```

## Task 5: Final Verification And Cleanup

**Files:**
- Inspect: all files changed by Tasks 1-4
- Modify only if verification exposes a concrete failure.

- [ ] **Step 1: Run formatter/linter**

Run: `uv run ruff check .`

Expected: PASS with no lint errors.

- [ ] **Step 2: Run targeted test set**

Run: `uv run pytest tests/diff tests/test_cli_diff.py -v`

Expected: PASS.

- [ ] **Step 3: Run full suite**

Run: `uv run pytest`

Expected: PASS.

- [ ] **Step 4: Run quality gate**

Run: `uv run python scripts/quality_gate.py`

Expected: PASS, ending with `[quality-gate] COMPLETE`.

- [ ] **Step 5: Confirm no dependency drift**

Run: `git diff -- pyproject.toml uv.lock`

Expected: no output.

- [ ] **Step 6: Inspect final diff**

Run: `git status --short`

Expected: only intentional files are changed or no changes if every task was already committed.

Run: `git log --oneline -5`

Expected: recent commits include the Task 1-4 implementation commits.

- [ ] **Step 7: Fix verification failures if any**

If any verification command fails, make the smallest targeted fix, rerun the failing command, then rerun downstream verification from Step 1. Commit fixes with a Lore-protocol commit message that states the exact failing command in `Tested:`.

- [ ] **Step 8: Final report**

Report:

- changed files
- verification commands and outcomes
- known gaps
- example usage:

```bash
uv run loop-apidoc diff --base ./output/<old-run> --head ./output/<new-run>
```

## Self-Review Checklist

- Spec coverage:
  - CLI command: Task 4.
  - JSON/Markdown report writing: Task 3 and Task 4.
  - Impact classes: Task 2 and Task 3.
  - OpenAPI comparison: Task 2.
  - Integration contract comparison: Task 3.
  - Provenance/validation/manifest source-only comparison: Task 3.
  - No Markdown guide or examples comparison: Scope constraints and README wording in Task 4.
  - Invalid input exit `2` and no premature output: Task 1 loader and Task 4 CLI tests.
  - No new dependency: Task 5.
- Type consistency:
  - `DiffImpact` values match summary keys.
  - `DiffReport.summary` is `dict[str, int]` and includes all four impact classes.
  - `RunArtifacts` uses existing `ProvenanceDocument`, `ValidationReport`, and `Manifest`.
  - `build_diff_report(base: RunArtifacts, head: RunArtifacts) -> DiffReport` is the single compare entry point.
- Verification sequence:
  - Focused tests first.
  - Then all diff/CLI tests.
  - Then ruff, full suite, quality gate.
