# Foundry API Asset Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a project-local `.foundry/api/` asset governance layer that imports completed `loop-apidoc` run directories into docsets as candidates, promotes them to approved versioned assets, and exposes a deterministic "current" pointer for downstream work.

**Architecture:** A new pure-plus-IO package `loop_apidoc/foundry/` following the exact shape of `diff/` and `score/`: `models.py` (pydantic + str-Enums + typed errors), `paths.py` (pure filesystem layout), `store.py` (governance-JSON read/write), three operation modules (`register.py`, `importer.py`, `approve.py`), a read-side `query.py`, and a Typer sub-app in `foundry/cli.py` wired into the root CLI as `loop-apidoc foundry <cmd>`. Assets are **self-contained**: run artifacts are copied into `.foundry/`, never referenced by path. Generation (the existing plugin/CLI) is untouched — assetization is a separate, explicit step.

**Tech Stack:** Python ≥3.11, pydantic v2, typer, pyyaml (transitively via the reused `diff` loader), `shutil` for tree copies. Managed with `uv`. Tests with pytest.

## Global Constraints

- Python `>=3.11`; managed with `uv` (no `pip`). Run everything via `uv run ...`.
- Pydantic **v2**. Every module starts with `from __future__ import annotations`. Domain/report models are plain `class X(BaseModel)` with snake_case fields and **no aliases**; enums are `class X(str, Enum)` with lowercase string values.
- Immutability: pure functions return new values; only the designated IO modules touch the filesystem.
- Typed input errors subclass `ValueError` (mirroring `DiffInputError` / `ScoreInputError`).
- CLI exit-code convention: `0` = success, `1` = ran but failed a gate (e.g. approval refused), `2` = input error (missing docset/candidate/run artifact). Input-error commands catch the package error and `raise typer.Exit(code=2) from exc`.
- Traditional-Chinese help strings on CLI options/commands (token-economy English is only for `SKILL.md`).
- Canonical JSON write is `model.model_dump_json(indent=2)` then `Path.write_text(..., encoding="utf-8")`. Read with `Model.model_validate_json(text)`.
- The core contract rule is preserved: `openapi.yaml` and `integration-contract.json` are authoritative; everything else is derived. Foundry copies them verbatim, never rewrites them.
- Tests mirror the package tree under `tests/foundry/`, one `test_<module>.py` per source module; CLI tests are flat at `tests/test_cli_foundry.py`. Use a fixed `_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)`; never call wall-clock `datetime.now()` inside pure code (pass `now` in, like `make_run_id`).

---

### Task 1: Package skeleton, models, and typed errors

**Files:**
- Create: `loop_apidoc/foundry/__init__.py`
- Create: `loop_apidoc/foundry/models.py`
- Create: `tests/foundry/__init__.py`
- Test: `tests/foundry/test_models.py`

**Interfaces:**
- Produces (imported by every later task):
  - `AssetStatus(str, Enum)`: `CANDIDATE="candidate"`, `APPROVED="approved"`, `SUPERSEDED="superseded"`, `REJECTED="rejected"`, `DEPRECATED="deprecated"`
  - `SourceRole(str, Enum)`: `PRIMARY="primary"`, `SUPPLEMENTAL="supplemental"`
  - `SourceRef(BaseModel)`: `kind: str`, `path: str`, `role: SourceRole = SourceRole.PRIMARY`
  - `Docset(BaseModel)`: `docset_id: str`, `title: str`, `provider: str`, `product: str`, `source_scope: str = ""`, `current_asset: str | None = None`, `sources: list[SourceRef] = []`
  - `AssetValidation(BaseModel)`: `ok: bool`, `score: int | None = None`
  - `AssetArtifacts(BaseModel)`: `openapi: str`, `provenance: str`, `validation: str`, `integration_contract: str | None = None`, `review: str | None = None`, `score: str | None = None`, `handoff: str | None = None`
  - `Asset(BaseModel)`: `asset_id`, `docset_id`, `status: AssetStatus`, `run_id`, `generated_at: str`, `source_hashes: list[str] = []`, `validation: AssetValidation`, `artifacts: AssetArtifacts`, `supersedes: str | None = None`, `approved_at: str | None = None`, `approved_by: str | None = None`, `known_gaps: list[str] = []`
  - `CurrentPointer(BaseModel)`: `current_asset: str`, `status: AssetStatus`, `validation: AssetValidation`, `generated_at: str`, `approved_at: str | None = None`, `artifacts: AssetArtifacts`
  - `CatalogDocsetEntry(BaseModel)`: `docset_id`, `title`, `provider`, `product`, `current_asset: str | None = None`
  - `Catalog(BaseModel)`: `version: int = 1`, `docsets: list[CatalogDocsetEntry] = []`
  - `FoundryInputError(ValueError)`, `FoundryApprovalError(ValueError)`
  - `make_asset_id(docset_id: str, now: datetime) -> str` → `"{docset_id}-{now:%Y%m%d-%H%M%S}"`

- [ ] **Step 1: Create the empty package markers**

Create `loop_apidoc/foundry/__init__.py` with a single line:

```python
"""Foundry API project-local asset governance layer."""
```

Create `tests/foundry/__init__.py` as an empty file (zero bytes).

- [ ] **Step 2: Write the failing test**

Create `tests/foundry/test_models.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.foundry.models import (
    Asset,
    AssetArtifacts,
    AssetStatus,
    AssetValidation,
    Catalog,
    CatalogDocsetEntry,
    CurrentPointer,
    Docset,
    FoundryApprovalError,
    FoundryInputError,
    SourceRef,
    SourceRole,
    make_asset_id,
)

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)


def test_make_asset_id_matches_spec_format() -> None:
    assert make_asset_id("tappay-backend", _NOW) == "tappay-backend-20260702-120000"


def test_source_ref_defaults_to_primary_role() -> None:
    ref = SourceRef(kind="file", path="sources/x.md")
    assert ref.role is SourceRole.PRIMARY


def test_docset_round_trips_through_json() -> None:
    docset = Docset(
        docset_id="tappay-backend",
        title="TapPay Backend API",
        provider="tappay",
        product="backend-api",
        source_scope="Payment backend API documents",
        sources=[
            SourceRef(kind="file", path="sources/tappay/backend.md", role=SourceRole.PRIMARY),
            SourceRef(kind="file", path="sources/tappay/errors.md", role=SourceRole.SUPPLEMENTAL),
        ],
    )
    restored = Docset.model_validate_json(docset.model_dump_json())
    assert restored == docset
    assert restored.current_asset is None


def test_asset_round_trips_and_defaults() -> None:
    asset = Asset(
        asset_id="tappay-backend-20260702-120000",
        docset_id="tappay-backend",
        status=AssetStatus.APPROVED,
        run_id="20260702T120000.000000Z",
        generated_at="2026-07-02T12:00:00+00:00",
        validation=AssetValidation(ok=True, score=92),
        artifacts=AssetArtifacts(
            openapi="artifacts/openapi.yaml",
            provenance="artifacts/provenance.json",
            validation="artifacts/validation/report.json",
        ),
        approved_by="human-review",
        approved_at="2026-07-02T12:30:00+00:00",
    )
    restored = Asset.model_validate_json(asset.model_dump_json())
    assert restored == asset
    assert restored.supersedes is None
    assert restored.source_hashes == []
    assert restored.known_gaps == []


def test_current_pointer_and_catalog_construct() -> None:
    pointer = CurrentPointer(
        current_asset="tappay-backend-20260702-120000",
        status=AssetStatus.APPROVED,
        validation=AssetValidation(ok=True, score=92),
        generated_at="2026-07-02T12:00:00+00:00",
        artifacts=AssetArtifacts(
            openapi="artifacts/openapi.yaml",
            provenance="artifacts/provenance.json",
            validation="artifacts/validation/report.json",
        ),
    )
    catalog = Catalog(docsets=[CatalogDocsetEntry(
        docset_id="tappay-backend",
        title="TapPay Backend API",
        provider="tappay",
        product="backend-api",
        current_asset=pointer.current_asset,
    )])
    assert catalog.version == 1
    assert Catalog.model_validate_json(catalog.model_dump_json()) == catalog


def test_errors_are_value_errors() -> None:
    assert issubclass(FoundryInputError, ValueError)
    assert issubclass(FoundryApprovalError, ValueError)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/foundry/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.foundry.models'`

- [ ] **Step 4: Write minimal implementation**

Create `loop_apidoc/foundry/models.py`:

```python
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AssetStatus(str, Enum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class SourceRole(str, Enum):
    PRIMARY = "primary"
    SUPPLEMENTAL = "supplemental"


class FoundryInputError(ValueError):
    """A Foundry operation cannot proceed because a docset, candidate, or run
    artifact is missing or invalid."""


class FoundryApprovalError(ValueError):
    """A candidate cannot be approved because it fails an approval gate
    (validation not ok, or score below the required minimum)."""


class SourceRef(BaseModel):
    kind: str
    path: str
    role: SourceRole = SourceRole.PRIMARY


class Docset(BaseModel):
    docset_id: str
    title: str
    provider: str
    product: str
    source_scope: str = ""
    current_asset: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)


class AssetValidation(BaseModel):
    ok: bool
    score: int | None = None


class AssetArtifacts(BaseModel):
    openapi: str
    provenance: str
    validation: str
    integration_contract: str | None = None
    review: str | None = None
    score: str | None = None
    handoff: str | None = None


class Asset(BaseModel):
    asset_id: str
    docset_id: str
    status: AssetStatus
    run_id: str
    generated_at: str
    source_hashes: list[str] = Field(default_factory=list)
    validation: AssetValidation
    artifacts: AssetArtifacts
    supersedes: str | None = None
    approved_at: str | None = None
    approved_by: str | None = None
    known_gaps: list[str] = Field(default_factory=list)


class CurrentPointer(BaseModel):
    current_asset: str
    status: AssetStatus
    validation: AssetValidation
    generated_at: str
    approved_at: str | None = None
    artifacts: AssetArtifacts


class CatalogDocsetEntry(BaseModel):
    docset_id: str
    title: str
    provider: str
    product: str
    current_asset: str | None = None


class Catalog(BaseModel):
    version: int = 1
    docsets: list[CatalogDocsetEntry] = Field(default_factory=list)


def make_asset_id(docset_id: str, now: datetime) -> str:
    """Mint a human-readable asset id, e.g. tappay-backend-20260702-120000."""
    return f"{docset_id}-{now.strftime('%Y%m%d-%H%M%S')}"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/foundry/test_models.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Commit**

```bash
git add loop_apidoc/foundry/__init__.py loop_apidoc/foundry/models.py tests/foundry/__init__.py tests/foundry/test_models.py
git commit -m "feat: [foundry] add asset-model pydantic models and typed errors"
```

---

### Task 2: Filesystem layout helpers (pure)

**Files:**
- Create: `loop_apidoc/foundry/paths.py`
- Test: `tests/foundry/test_paths.py`

**Interfaces:**
- Consumes: nothing (pure `pathlib` math)
- Produces (all take `project_root: Path` first):
  - `foundry_api_root(project_root) -> Path` → `<root>/.foundry/api`
  - `catalog_path(project_root) -> Path` → `.../catalog.json`
  - `docsets_root(project_root) -> Path` → `.../docsets`
  - `docset_dir(project_root, docset_id) -> Path`
  - `docset_manifest_path(project_root, docset_id) -> Path` → `.../docset.json`
  - `current_path(project_root, docset_id) -> Path` → `.../current.json`
  - `candidates_dir(project_root, docset_id) -> Path`
  - `candidate_dir(project_root, docset_id, run_id) -> Path`
  - `assets_dir(project_root, docset_id) -> Path`
  - `asset_dir(project_root, docset_id, asset_id) -> Path`
  - `asset_manifest_path(project_root, docset_id, asset_id) -> Path` → `.../asset.json`
  - `asset_artifacts_dir(project_root, docset_id, asset_id) -> Path` → `.../artifacts`

- [ ] **Step 1: Write the failing test**

Create `tests/foundry/test_paths.py`:

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.foundry import paths


def test_layout_matches_spec_shape() -> None:
    root = Path("/proj")
    assert paths.foundry_api_root(root) == root / ".foundry" / "api"
    assert paths.catalog_path(root) == root / ".foundry" / "api" / "catalog.json"
    assert paths.docsets_root(root) == root / ".foundry" / "api" / "docsets"

    ds = paths.docset_dir(root, "tappay-backend")
    assert ds == root / ".foundry" / "api" / "docsets" / "tappay-backend"
    assert paths.docset_manifest_path(root, "tappay-backend") == ds / "docset.json"
    assert paths.current_path(root, "tappay-backend") == ds / "current.json"
    assert paths.candidates_dir(root, "tappay-backend") == ds / "candidates"
    assert paths.candidate_dir(root, "tappay-backend", "run-1") == ds / "candidates" / "run-1"
    assert paths.assets_dir(root, "tappay-backend") == ds / "assets"

    asset = paths.asset_dir(root, "tappay-backend", "a-1")
    assert asset == ds / "assets" / "a-1"
    assert paths.asset_manifest_path(root, "tappay-backend", "a-1") == asset / "asset.json"
    assert paths.asset_artifacts_dir(root, "tappay-backend", "a-1") == asset / "artifacts"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foundry/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.foundry.paths'`

- [ ] **Step 3: Write minimal implementation**

Create `loop_apidoc/foundry/paths.py`:

```python
from __future__ import annotations

from pathlib import Path

FOUNDRY_DIR = ".foundry"
API_DIR = "api"


def foundry_api_root(project_root: Path) -> Path:
    return project_root / FOUNDRY_DIR / API_DIR


def catalog_path(project_root: Path) -> Path:
    return foundry_api_root(project_root) / "catalog.json"


def docsets_root(project_root: Path) -> Path:
    return foundry_api_root(project_root) / "docsets"


def docset_dir(project_root: Path, docset_id: str) -> Path:
    return docsets_root(project_root) / docset_id


def docset_manifest_path(project_root: Path, docset_id: str) -> Path:
    return docset_dir(project_root, docset_id) / "docset.json"


def current_path(project_root: Path, docset_id: str) -> Path:
    return docset_dir(project_root, docset_id) / "current.json"


def candidates_dir(project_root: Path, docset_id: str) -> Path:
    return docset_dir(project_root, docset_id) / "candidates"


def candidate_dir(project_root: Path, docset_id: str, run_id: str) -> Path:
    return candidates_dir(project_root, docset_id) / run_id


def assets_dir(project_root: Path, docset_id: str) -> Path:
    return docset_dir(project_root, docset_id) / "assets"


def asset_dir(project_root: Path, docset_id: str, asset_id: str) -> Path:
    return assets_dir(project_root, docset_id) / asset_id


def asset_manifest_path(project_root: Path, docset_id: str, asset_id: str) -> Path:
    return asset_dir(project_root, docset_id, asset_id) / "asset.json"


def asset_artifacts_dir(project_root: Path, docset_id: str, asset_id: str) -> Path:
    return asset_dir(project_root, docset_id, asset_id) / "artifacts"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/foundry/test_paths.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/foundry/paths.py tests/foundry/test_paths.py
git commit -m "feat: [foundry] add filesystem layout helpers"
```

---

### Task 3: Governance-JSON store (read/write)

**Files:**
- Create: `loop_apidoc/foundry/store.py`
- Test: `tests/foundry/test_store.py`

**Interfaces:**
- Consumes: `models` (all), `paths` (all), `FoundryInputError`
- Produces:
  - `load_catalog(project_root) -> Catalog` — returns empty `Catalog()` if `catalog.json` is absent; raises `FoundryInputError` on unreadable/invalid JSON.
  - `save_catalog(project_root, catalog) -> None`
  - `load_docset(project_root, docset_id) -> Docset` — raises `FoundryInputError` if `docset.json` missing/invalid.
  - `save_docset(project_root, docset) -> None`
  - `load_asset(project_root, docset_id, asset_id) -> Asset` — raises `FoundryInputError` if missing/invalid.
  - `save_asset(project_root, asset) -> None`
  - `load_current(project_root, docset_id) -> CurrentPointer | None` — `None` if absent; raises on invalid.
  - `save_current(project_root, docset_id, pointer) -> None`
  - `upsert_catalog_entry(catalog: Catalog, entry: CatalogDocsetEntry) -> Catalog` — **pure**; returns a new `Catalog` with the entry replacing any same-`docset_id` entry (order preserved; appended if new).

- [ ] **Step 1: Write the failing test**

Create `tests/foundry/test_store.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.models import (
    Asset,
    AssetArtifacts,
    AssetStatus,
    AssetValidation,
    Catalog,
    CatalogDocsetEntry,
    CurrentPointer,
    Docset,
    FoundryInputError,
)


def _docset() -> Docset:
    return Docset(
        docset_id="tappay-backend",
        title="TapPay Backend API",
        provider="tappay",
        product="backend-api",
    )


def _asset() -> Asset:
    return Asset(
        asset_id="tappay-backend-20260702-120000",
        docset_id="tappay-backend",
        status=AssetStatus.APPROVED,
        run_id="20260702T120000.000000Z",
        generated_at="2026-07-02T12:00:00+00:00",
        validation=AssetValidation(ok=True, score=92),
        artifacts=AssetArtifacts(
            openapi="artifacts/openapi.yaml",
            provenance="artifacts/provenance.json",
            validation="artifacts/validation/report.json",
        ),
    )


def test_catalog_missing_returns_empty(tmp_path: Path) -> None:
    assert store.load_catalog(tmp_path) == Catalog()


def test_catalog_round_trip(tmp_path: Path) -> None:
    catalog = Catalog(docsets=[CatalogDocsetEntry(
        docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"
    )])
    store.save_catalog(tmp_path, catalog)
    assert paths.catalog_path(tmp_path).is_file()
    assert store.load_catalog(tmp_path) == catalog


def test_docset_round_trip(tmp_path: Path) -> None:
    store.save_docset(tmp_path, _docset())
    assert store.load_docset(tmp_path, "tappay-backend") == _docset()


def test_missing_docset_raises_input_error(tmp_path: Path) -> None:
    with pytest.raises(FoundryInputError, match="docset.json"):
        store.load_docset(tmp_path, "nope")


def test_asset_round_trip(tmp_path: Path) -> None:
    store.save_asset(tmp_path, _asset())
    loaded = store.load_asset(tmp_path, "tappay-backend", "tappay-backend-20260702-120000")
    assert loaded == _asset()


def test_current_absent_returns_none(tmp_path: Path) -> None:
    assert store.load_current(tmp_path, "tappay-backend") is None


def test_current_round_trip(tmp_path: Path) -> None:
    pointer = CurrentPointer(
        current_asset="tappay-backend-20260702-120000",
        status=AssetStatus.APPROVED,
        validation=AssetValidation(ok=True, score=92),
        generated_at="2026-07-02T12:00:00+00:00",
        artifacts=_asset().artifacts,
    )
    store.save_current(tmp_path, "tappay-backend", pointer)
    assert store.load_current(tmp_path, "tappay-backend") == pointer


def test_invalid_json_raises_input_error(tmp_path: Path) -> None:
    path = paths.docset_manifest_path(tmp_path, "tappay-backend")
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(FoundryInputError, match="docset.json"):
        store.load_docset(tmp_path, "tappay-backend")


def test_upsert_catalog_entry_replaces_and_appends() -> None:
    base = Catalog(docsets=[
        CatalogDocsetEntry(docset_id="a", title="A", provider="p", product="x"),
        CatalogDocsetEntry(docset_id="b", title="B", provider="p", product="y"),
    ])
    replaced = store.upsert_catalog_entry(
        base, CatalogDocsetEntry(docset_id="a", title="A2", provider="p", product="x", current_asset="a-1")
    )
    assert [d.docset_id for d in replaced.docsets] == ["a", "b"]
    assert replaced.docsets[0].title == "A2"
    assert replaced.docsets[0].current_asset == "a-1"
    # original is untouched (immutability)
    assert base.docsets[0].title == "A"

    appended = store.upsert_catalog_entry(
        base, CatalogDocsetEntry(docset_id="c", title="C", provider="p", product="z")
    )
    assert [d.docset_id for d in appended.docsets] == ["a", "b", "c"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foundry/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.foundry.store'`

- [ ] **Step 3: Write minimal implementation**

Create `loop_apidoc/foundry/store.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from loop_apidoc.foundry import paths
from loop_apidoc.foundry.models import (
    Asset,
    Catalog,
    CatalogDocsetEntry,
    CurrentPointer,
    Docset,
    FoundryInputError,
)

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _write_model(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def _read_model(model: type[_ModelT], path: Path, label: str) -> _ModelT:
    if not path.is_file():
        raise FoundryInputError(f"required file missing: {label}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FoundryInputError(f"cannot read {label}: {str(exc)[:200]}") from exc
    try:
        return model.model_validate_json(text)
    except ValidationError as exc:
        raise FoundryInputError(f"{label} is invalid: {str(exc)[:200]}") from exc
    except ValueError as exc:  # non-JSON text
        raise FoundryInputError(f"{label} is not valid JSON: {str(exc)[:200]}") from exc


def load_catalog(project_root: Path) -> Catalog:
    path = paths.catalog_path(project_root)
    if not path.is_file():
        return Catalog()
    return _read_model(Catalog, path, "catalog.json")


def save_catalog(project_root: Path, catalog: Catalog) -> None:
    _write_model(paths.catalog_path(project_root), catalog)


def load_docset(project_root: Path, docset_id: str) -> Docset:
    return _read_model(
        Docset, paths.docset_manifest_path(project_root, docset_id), "docset.json"
    )


def save_docset(project_root: Path, docset: Docset) -> None:
    _write_model(paths.docset_manifest_path(project_root, docset.docset_id), docset)


def load_asset(project_root: Path, docset_id: str, asset_id: str) -> Asset:
    return _read_model(
        Asset, paths.asset_manifest_path(project_root, docset_id, asset_id), "asset.json"
    )


def save_asset(project_root: Path, asset: Asset) -> None:
    _write_model(
        paths.asset_manifest_path(project_root, asset.docset_id, asset.asset_id), asset
    )


def load_current(project_root: Path, docset_id: str) -> CurrentPointer | None:
    path = paths.current_path(project_root, docset_id)
    if not path.is_file():
        return None
    return _read_model(CurrentPointer, path, "current.json")


def save_current(project_root: Path, docset_id: str, pointer: CurrentPointer) -> None:
    _write_model(paths.current_path(project_root, docset_id), pointer)


def upsert_catalog_entry(catalog: Catalog, entry: CatalogDocsetEntry) -> Catalog:
    replaced = False
    docsets: list[CatalogDocsetEntry] = []
    for existing in catalog.docsets:
        if existing.docset_id == entry.docset_id:
            docsets.append(entry)
            replaced = True
        else:
            docsets.append(existing)
    if not replaced:
        docsets.append(entry)
    return Catalog(version=catalog.version, docsets=docsets)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/foundry/test_store.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/foundry/store.py tests/foundry/test_store.py
git commit -m "feat: [foundry] add governance-json store and catalog upsert"
```

---

### Task 4: Register a docset

**Files:**
- Create: `loop_apidoc/foundry/register.py`
- Test: `tests/foundry/test_register.py`

**Interfaces:**
- Consumes: `store` (`load_docset`, `save_docset`, `load_catalog`, `save_catalog`, `upsert_catalog_entry`), `paths.docset_manifest_path`, `models.Docset`, `models.CatalogDocsetEntry`, `models.FoundryInputError`
- Produces:
  - `register_docset(project_root: Path, docset: Docset, *, exist_ok: bool = False) -> Docset` — writes `docset.json`, upserts the catalog entry, returns the persisted docset. Raises `FoundryInputError` if the docset already exists and `exist_ok` is `False`. When `exist_ok` is `True` and the docset exists, it **preserves** the existing `current_asset` (re-registration must not silently drop the current pointer).

- [ ] **Step 1: Write the failing test**

Create `tests/foundry/test_register.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from loop_apidoc.foundry import register, store
from loop_apidoc.foundry.models import Docset, FoundryInputError, SourceRef, SourceRole


def _docset(**overrides: object) -> Docset:
    base = dict(
        docset_id="tappay-backend",
        title="TapPay Backend API",
        provider="tappay",
        product="backend-api",
        source_scope="Payment backend API documents",
        sources=[
            SourceRef(kind="file", path="sources/tappay/backend.md", role=SourceRole.PRIMARY),
        ],
    )
    base.update(overrides)
    return Docset(**base)  # type: ignore[arg-type]


def test_register_writes_docset_and_catalog(tmp_path: Path) -> None:
    result = register.register_docset(tmp_path, _docset())
    assert result.docset_id == "tappay-backend"
    assert store.load_docset(tmp_path, "tappay-backend") == _docset()
    catalog = store.load_catalog(tmp_path)
    assert [d.docset_id for d in catalog.docsets] == ["tappay-backend"]
    assert catalog.docsets[0].title == "TapPay Backend API"
    assert catalog.docsets[0].current_asset is None


def test_register_existing_without_exist_ok_raises(tmp_path: Path) -> None:
    register.register_docset(tmp_path, _docset())
    with pytest.raises(FoundryInputError, match="already exists"):
        register.register_docset(tmp_path, _docset(title="Changed"))


def test_register_exist_ok_updates_and_preserves_current_asset(tmp_path: Path) -> None:
    register.register_docset(tmp_path, _docset())
    # simulate a prior approval having set current_asset
    existing = store.load_docset(tmp_path, "tappay-backend")
    store.save_docset(tmp_path, existing.model_copy(update={"current_asset": "tappay-backend-1"}))

    updated = register.register_docset(tmp_path, _docset(title="New Title"), exist_ok=True)
    assert updated.title == "New Title"
    assert updated.current_asset == "tappay-backend-1"
    assert store.load_catalog(tmp_path).docsets[0].current_asset == "tappay-backend-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foundry/test_register.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.foundry.register'`

- [ ] **Step 3: Write minimal implementation**

Create `loop_apidoc/foundry/register.py`:

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.models import CatalogDocsetEntry, Docset, FoundryInputError


def register_docset(
    project_root: Path, docset: Docset, *, exist_ok: bool = False
) -> Docset:
    manifest_path = paths.docset_manifest_path(project_root, docset.docset_id)
    if manifest_path.is_file():
        if not exist_ok:
            raise FoundryInputError(
                f"docset already exists: {docset.docset_id} (use exist_ok to update)"
            )
        existing = store.load_docset(project_root, docset.docset_id)
        docset = docset.model_copy(update={"current_asset": existing.current_asset})

    store.save_docset(project_root, docset)
    catalog = store.upsert_catalog_entry(
        store.load_catalog(project_root),
        CatalogDocsetEntry(
            docset_id=docset.docset_id,
            title=docset.title,
            provider=docset.provider,
            product=docset.product,
            current_asset=docset.current_asset,
        ),
    )
    store.save_catalog(project_root, catalog)
    return docset
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/foundry/test_register.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/foundry/register.py tests/foundry/test_register.py
git commit -m "feat: [foundry] add docset registration"
```

---

### Task 5: Import a run as a candidate

**Files:**
- Create: `loop_apidoc/foundry/importer.py`
- Create: `tests/foundry/_fixtures.py` (shared run-dir builder, reused by Tasks 6 & 8)
- Test: `tests/foundry/test_importer.py`

**Interfaces:**
- Consumes: `store.load_docset`, `paths.candidate_dir`, `models.FoundryInputError`, and the existing `loop_apidoc.diff.loader.load_run_artifacts` / `DiffInputError` (reused to validate the run dir has the required artifacts).
- Produces:
  - `@dataclass(frozen=True) ImportResult`: `run_id: str`, `candidate_dir: Path`
  - `import_run(project_root: Path, docset_id: str, run_dir: Path, *, overwrite: bool = False) -> ImportResult` — validates the docset exists and the run dir is a completed run (via `load_run_artifacts`), derives `run_id` from `run_dir.name`, copies the entire run tree into `candidate_dir`, and returns the result. Raises `FoundryInputError` if the docset is missing, the run dir is not a valid run, or the candidate already exists and `overwrite` is `False`.

- [ ] **Step 1: Write the shared run-dir fixture**

Create `tests/foundry/_fixtures.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.validate.models import ValidationReport

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "paths": {"/ping": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }


def write_run_dir(
    run_dir: Path,
    *,
    validation_ok: bool = True,
    score: int | None = 92,
    with_integration: bool = True,
) -> Path:
    """Materialize a completed run dir accepted by diff.load_run_artifacts."""
    run_dir.mkdir(parents=True)
    (run_dir / "openapi.yaml").write_text(
        yaml.safe_dump(_openapi(), sort_keys=False), encoding="utf-8"
    )
    provenance = ProvenanceDocument(
        notebook_url="",
        entries=[
            ProvenanceEntry(
                target="paths./ping.get",
                status=PlanItemStatus.SUPPORTED,
                manifest_source="manual.md",
                query_id="06",
                answer_path="answers/06.txt",
                locator="p.1",
            )
        ],
    )
    (run_dir / "provenance.json").write_text(
        provenance.model_dump_json(indent=2), encoding="utf-8"
    )
    validation_dir = run_dir / "validation"
    validation_dir.mkdir()
    report = ValidationReport() if validation_ok else _failing_report()
    (validation_dir / "report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    (validation_dir / "report.md").write_text("# Validation\n", encoding="utf-8")
    manifest = Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=10,
                sha256="hash-manual",
                scanned_at=_NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    (run_dir / "review.html").write_text("<html></html>", encoding="utf-8")
    if with_integration:
        (run_dir / "integration-contract.json").write_text(
            '{"payloads": []}', encoding="utf-8"
        )
    if score is not None:
        score_dir = run_dir / "score"
        score_dir.mkdir()
        (score_dir / "score.json").write_text(
            _score_json(score), encoding="utf-8"
        )
        (score_dir / "score.md").write_text("# Score\n", encoding="utf-8")
    handoff_dir = run_dir / "handoff"
    handoff_dir.mkdir()
    (handoff_dir / "sdk-hints.json").write_text("{}", encoding="utf-8")
    return run_dir


def _failing_report() -> ValidationReport:
    from loop_apidoc.validate.models import Issue, IssueSeverity

    return ValidationReport(
        issues=[
            Issue(
                code="REQUIRED_INFO_MISSING",
                severity=IssueSeverity.ERROR,
                message="missing",
                target="paths./ping.get",
            )
        ]
    )


def _score_json(score: int) -> str:
    from loop_apidoc.score.models import ScoreProfile, ScoreReport, ScoreStatus

    return ScoreReport(
        status=ScoreStatus.PASS,
        score=score,
        profile=ScoreProfile.CI,
        min_score=0,
        category_scores={},
    ).model_dump_json(indent=2)
```

> **Note for the implementer:** Before relying on the `Issue` / `IssueSeverity` / `ScoreReport` / `ScoreStatus` constructor shapes above, open `loop_apidoc/validate/models.py` and `loop_apidoc/score/models.py` and confirm the exact required fields; adjust the fixture to satisfy them (the required-field set is small and stable, but must match). The rest of the fixture (openapi/provenance/manifest) is copied verbatim from the working `tests/score/test_loader.py` builder and is known-good.

- [ ] **Step 2: Write the failing test**

Create `tests/foundry/test_importer.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from loop_apidoc.foundry import importer, paths, register
from loop_apidoc.foundry.models import Docset, FoundryInputError
from tests.foundry._fixtures import write_run_dir

_RUN_ID = "20260702T120000.000000Z"


def _register(tmp_path: Path) -> None:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )


def test_import_copies_run_into_candidate(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)

    result = importer.import_run(tmp_path, "tappay-backend", run_dir)

    assert result.run_id == _RUN_ID
    dest = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    assert result.candidate_dir == dest
    assert (dest / "openapi.yaml").is_file()
    assert (dest / "validation" / "report.json").is_file()
    assert (dest / "handoff" / "sdk-hints.json").is_file()


def test_import_missing_docset_raises(tmp_path: Path) -> None:
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    with pytest.raises(FoundryInputError, match="docset.json"):
        importer.import_run(tmp_path, "nope", run_dir)


def test_import_incomplete_run_raises(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    (run_dir / "openapi.yaml").unlink()
    with pytest.raises(FoundryInputError, match="openapi.yaml"):
        importer.import_run(tmp_path, "tappay-backend", run_dir)


def test_import_duplicate_candidate_raises_without_overwrite(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    with pytest.raises(FoundryInputError, match="candidate already exists"):
        importer.import_run(tmp_path, "tappay-backend", run_dir)


def test_import_overwrite_replaces_candidate(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    result = importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)
    assert result.candidate_dir.is_dir()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/foundry/test_importer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.foundry.importer'`

- [ ] **Step 4: Write minimal implementation**

Create `loop_apidoc/foundry/importer.py`:

```python
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from loop_apidoc.diff.loader import DiffInputError, load_run_artifacts
from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.models import FoundryInputError


@dataclass(frozen=True)
class ImportResult:
    run_id: str
    candidate_dir: Path


def import_run(
    project_root: Path,
    docset_id: str,
    run_dir: Path,
    *,
    overwrite: bool = False,
) -> ImportResult:
    # Fail fast if the docset is unknown.
    store.load_docset(project_root, docset_id)

    if not run_dir.is_dir():
        raise FoundryInputError(f"run directory does not exist: {run_dir}")

    # Reuse the diff loader as the completeness gate for a run dir.
    try:
        load_run_artifacts(run_dir)
    except DiffInputError as exc:
        raise FoundryInputError(f"run directory is not a valid run: {exc}") from exc

    run_id = run_dir.name
    dest = paths.candidate_dir(project_root, docset_id, run_id)
    if dest.exists():
        if not overwrite:
            raise FoundryInputError(f"candidate already exists: {run_id}")
        shutil.rmtree(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(run_dir, dest)
    return ImportResult(run_id=run_id, candidate_dir=dest)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/foundry/test_importer.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add loop_apidoc/foundry/importer.py tests/foundry/_fixtures.py tests/foundry/test_importer.py
git commit -m "feat: [foundry] import a completed run as a docset candidate"
```

---

### Task 6: Approve a candidate into a versioned asset

**Files:**
- Create: `loop_apidoc/foundry/approve.py`
- Test: `tests/foundry/test_approve.py`

**Interfaces:**
- Consumes: `store` (all load/save), `paths` (`candidate_dir`, `asset_artifacts_dir`), `models` (`Asset`, `AssetArtifacts`, `AssetStatus`, `AssetValidation`, `CurrentPointer`, `CatalogDocsetEntry`, `make_asset_id`, `FoundryInputError`, `FoundryApprovalError`), `diff.loader.load_run_artifacts`, and `loop_apidoc.score.models.ScoreReport`.
- Produces:
  - `approve_candidate(project_root: Path, docset_id: str, run_id: str, *, approved_by: str, now: datetime, min_score: int | None = None, allow_failing: bool = False, known_gaps: list[str] | None = None) -> Asset`

  Behavior:
  1. Load the docset (missing → `FoundryInputError`).
  2. Candidate dir must exist (missing → `FoundryInputError`).
  3. Load candidate artifacts via `load_run_artifacts` to read `validation.ok` and `manifest` (for `source_hashes`). Read optional `score/score.json` → `ScoreReport.score`.
  4. **Gate:** if `validation.ok` is `False` and not `allow_failing` → `FoundryApprovalError`. If `min_score` is set and (score is `None` or `< min_score`) → `FoundryApprovalError`.
  5. `asset_id = make_asset_id(docset_id, now)`.
  6. Copy the candidate tree into `asset_artifacts_dir` (must not already exist → `FoundryApprovalError`).
  7. Build `AssetArtifacts` recording only files that exist under the copied artifacts dir (openapi/provenance/validation always present; integration/review/score/handoff conditional).
  8. `supersedes = docset.current_asset`. If a prior current asset exists, load it, set its status to `SUPERSEDED`, save it.
  9. Write `asset.json` (status `APPROVED`, `approved_at=now.isoformat()`, `approved_by`, `source_hashes` from manifest, `generated_at` from `manifest.generated_at.isoformat()`, `known_gaps`).
  10. Write `current.json` (`CurrentPointer` caching status/validation/generated_at/approved_at/artifacts).
  11. Update `docset.current_asset` and save; upsert the catalog entry's `current_asset`.
  12. Return the `Asset`.

- [ ] **Step 1: Write the failing test**

Create `tests/foundry/test_approve.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.foundry import approve, importer, register, store
from loop_apidoc.foundry.models import (
    AssetStatus,
    Docset,
    FoundryApprovalError,
    FoundryInputError,
)
from tests.foundry._fixtures import write_run_dir

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
_LATER = datetime(2026, 7, 3, 9, 30, 0, tzinfo=timezone.utc)
_RUN_ID = "20260702T120000.000000Z"
_RUN_ID_2 = "20260703T090000.000000Z"


def _setup(tmp_path: Path, run_id: str = _RUN_ID, **run_kwargs: object) -> None:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )
    run_dir = write_run_dir(tmp_path / "output" / run_id, **run_kwargs)  # type: ignore[arg-type]
    importer.import_run(tmp_path, "tappay-backend", run_dir)


def test_approve_creates_asset_and_current(tmp_path: Path) -> None:
    _setup(tmp_path)

    asset = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="human-review", now=_NOW
    )

    assert asset.asset_id == "tappay-backend-20260702-120000"
    assert asset.status is AssetStatus.APPROVED
    assert asset.approved_by == "human-review"
    assert asset.approved_at == _NOW.isoformat()
    assert asset.validation.ok is True
    assert asset.validation.score == 92
    assert asset.source_hashes == ["hash-manual"]
    assert asset.supersedes is None

    # artifacts copied and self-contained
    art_dir = tmp_path / ".foundry" / "api" / "docsets" / "tappay-backend" / "assets" / asset.asset_id / "artifacts"
    assert (art_dir / "openapi.yaml").is_file()
    assert (art_dir / "handoff" / "sdk-hints.json").is_file()
    assert asset.artifacts.integration_contract == "artifacts/integration-contract.json"
    assert asset.artifacts.handoff == "artifacts/handoff/"
    assert asset.artifacts.score == "artifacts/score/score.json"

    # persisted + pointers updated
    assert store.load_asset(tmp_path, "tappay-backend", asset.asset_id) == asset
    current = store.load_current(tmp_path, "tappay-backend")
    assert current is not None
    assert current.current_asset == asset.asset_id
    assert current.validation.score == 92
    assert store.load_docset(tmp_path, "tappay-backend").current_asset == asset.asset_id
    assert store.load_catalog(tmp_path).docsets[0].current_asset == asset.asset_id


def test_approve_supersedes_previous_asset(tmp_path: Path) -> None:
    _setup(tmp_path)
    first = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    # import + approve a second run
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)
    second = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID_2, approved_by="a", now=_LATER
    )

    assert second.supersedes == first.asset_id
    reloaded_first = store.load_asset(tmp_path, "tappay-backend", first.asset_id)
    assert reloaded_first.status is AssetStatus.SUPERSEDED
    assert store.load_current(tmp_path, "tappay-backend").current_asset == second.asset_id


def test_approve_missing_candidate_raises_input_error(tmp_path: Path) -> None:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )
    with pytest.raises(FoundryInputError, match="candidate"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )


def test_approve_refuses_failing_validation(tmp_path: Path) -> None:
    _setup(tmp_path, validation_ok=False)
    with pytest.raises(FoundryApprovalError, match="validation"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )


def test_approve_allow_failing_overrides_gate(tmp_path: Path) -> None:
    _setup(tmp_path, validation_ok=False)
    asset = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW, allow_failing=True
    )
    assert asset.validation.ok is False
    assert asset.status is AssetStatus.APPROVED


def test_approve_refuses_below_min_score(tmp_path: Path) -> None:
    _setup(tmp_path, score=70)
    with pytest.raises(FoundryApprovalError, match="score"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="ci-score-90", now=_NOW, min_score=90
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foundry/test_approve.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.foundry.approve'`

- [ ] **Step 3: Write minimal implementation**

Create `loop_apidoc/foundry/approve.py`:

```python
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from loop_apidoc.diff.loader import DiffInputError, load_run_artifacts
from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.models import (
    Asset,
    AssetArtifacts,
    AssetStatus,
    AssetValidation,
    CatalogDocsetEntry,
    CurrentPointer,
    FoundryApprovalError,
    FoundryInputError,
    make_asset_id,
)


def _read_score(candidate_dir: Path) -> int | None:
    score_path = candidate_dir / "score" / "score.json"
    if not score_path.is_file():
        return None
    from loop_apidoc.score.models import ScoreReport

    try:
        return ScoreReport.model_validate_json(
            score_path.read_text(encoding="utf-8")
        ).score
    except ValueError:
        return None


def _build_artifacts(artifacts_dir: Path) -> AssetArtifacts:
    def rel(*parts: str) -> str | None:
        return "artifacts/" + "/".join(parts) if artifacts_dir.joinpath(*parts).exists() else None

    handoff = "artifacts/handoff/" if (artifacts_dir / "handoff").is_dir() else None
    return AssetArtifacts(
        openapi="artifacts/openapi.yaml",
        provenance="artifacts/provenance.json",
        validation="artifacts/validation/report.json",
        integration_contract=rel("integration-contract.json"),
        review=rel("review.html"),
        score=rel("score", "score.json"),
        handoff=handoff,
    )


def approve_candidate(
    project_root: Path,
    docset_id: str,
    run_id: str,
    *,
    approved_by: str,
    now: datetime,
    min_score: int | None = None,
    allow_failing: bool = False,
    known_gaps: list[str] | None = None,
) -> Asset:
    docset = store.load_docset(project_root, docset_id)

    candidate = paths.candidate_dir(project_root, docset_id, run_id)
    if not candidate.is_dir():
        raise FoundryInputError(f"candidate not found: {run_id}")

    try:
        run = load_run_artifacts(candidate)
    except DiffInputError as exc:
        raise FoundryInputError(f"candidate is not a valid run: {exc}") from exc

    validation_ok = run.validation.ok
    score = _read_score(candidate)

    if not validation_ok and not allow_failing:
        raise FoundryApprovalError(
            f"candidate {run_id} failed validation; pass allow_failing to override"
        )
    if min_score is not None and (score is None or score < min_score):
        raise FoundryApprovalError(
            f"candidate {run_id} score {score} is below required min_score {min_score}"
        )

    asset_id = make_asset_id(docset_id, now)
    artifacts_dir = paths.asset_artifacts_dir(project_root, docset_id, asset_id)
    if artifacts_dir.exists():
        raise FoundryApprovalError(f"asset already exists: {asset_id}")
    artifacts_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(candidate, artifacts_dir)

    source_hashes = [src.sha256 for src in run.manifest.local_sources]
    asset = Asset(
        asset_id=asset_id,
        docset_id=docset_id,
        status=AssetStatus.APPROVED,
        run_id=run_id,
        generated_at=run.manifest.generated_at.isoformat(),
        source_hashes=source_hashes,
        validation=AssetValidation(ok=validation_ok, score=score),
        artifacts=_build_artifacts(artifacts_dir),
        supersedes=docset.current_asset,
        approved_at=now.isoformat(),
        approved_by=approved_by,
        known_gaps=list(known_gaps or []),
    )

    if docset.current_asset:
        prior = store.load_asset(project_root, docset_id, docset.current_asset)
        store.save_asset(
            project_root, prior.model_copy(update={"status": AssetStatus.SUPERSEDED})
        )

    store.save_asset(project_root, asset)
    store.save_current(
        project_root,
        docset_id,
        CurrentPointer(
            current_asset=asset.asset_id,
            status=asset.status,
            validation=asset.validation,
            generated_at=asset.generated_at,
            approved_at=asset.approved_at,
            artifacts=asset.artifacts,
        ),
    )

    updated_docset = docset.model_copy(update={"current_asset": asset.asset_id})
    store.save_docset(project_root, updated_docset)
    store.save_catalog(
        project_root,
        store.upsert_catalog_entry(
            store.load_catalog(project_root),
            CatalogDocsetEntry(
                docset_id=docset.docset_id,
                title=docset.title,
                provider=docset.provider,
                product=docset.product,
                current_asset=asset.asset_id,
            ),
        ),
    )
    return asset
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/foundry/test_approve.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/foundry/approve.py tests/foundry/test_approve.py
git commit -m "feat: [foundry] approve candidate into versioned asset with supersession"
```

---

### Task 7: Read-side queries for downstream work

**Files:**
- Create: `loop_apidoc/foundry/query.py`
- Test: `tests/foundry/test_query.py`

**Interfaces:**
- Consumes: `store` (`load_current`, `load_asset`, `load_catalog`), `paths.asset_dir`, `models` (`Asset`, `Catalog`, `FoundryInputError`)
- Produces:
  - `load_current_asset(project_root: Path, docset_id: str) -> Asset` — resolves `current.json` → `asset.json`. Raises `FoundryInputError` if no current pointer exists.
  - `resolve_current_artifact(project_root: Path, docset_id: str, artifact: str) -> Path` — returns the absolute path to a named artifact (`"openapi"`, `"integration_contract"`, `"provenance"`, `"review"`, `"validation"`, `"score"`, `"handoff"`) of the current asset. Raises `FoundryInputError` if no current pointer, or the artifact field is unset/unknown.
  - `list_docsets(project_root: Path) -> Catalog` — thin alias over `store.load_catalog` (single downstream entry point).

- [ ] **Step 1: Write the failing test**

Create `tests/foundry/test_query.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.foundry import approve, importer, query, register
from loop_apidoc.foundry.models import Docset, FoundryInputError
from tests.foundry._fixtures import write_run_dir

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
_RUN_ID = "20260702T120000.000000Z"


def _approve(tmp_path: Path) -> str:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )
    importer.import_run(
        tmp_path, "tappay-backend", write_run_dir(tmp_path / "output" / _RUN_ID)
    )
    return approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    ).asset_id


def test_load_current_asset_returns_approved(tmp_path: Path) -> None:
    asset_id = _approve(tmp_path)
    asset = query.load_current_asset(tmp_path, "tappay-backend")
    assert asset.asset_id == asset_id
    assert asset.validation.score == 92


def test_load_current_asset_without_pointer_raises(tmp_path: Path) -> None:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )
    with pytest.raises(FoundryInputError, match="no current asset"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_resolve_current_artifact_returns_existing_path(tmp_path: Path) -> None:
    asset_id = _approve(tmp_path)
    openapi = query.resolve_current_artifact(tmp_path, "tappay-backend", "openapi")
    assert openapi.is_file()
    assert openapi.name == "openapi.yaml"
    assert asset_id in str(openapi)

    handoff = query.resolve_current_artifact(tmp_path, "tappay-backend", "handoff")
    assert handoff.is_dir()


def test_resolve_current_artifact_unknown_name_raises(tmp_path: Path) -> None:
    _approve(tmp_path)
    with pytest.raises(FoundryInputError, match="unknown artifact"):
        query.resolve_current_artifact(tmp_path, "tappay-backend", "bogus")


def test_list_docsets_returns_catalog(tmp_path: Path) -> None:
    _approve(tmp_path)
    catalog = query.list_docsets(tmp_path)
    assert [d.docset_id for d in catalog.docsets] == ["tappay-backend"]
    assert catalog.docsets[0].current_asset is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/foundry/test_query.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.foundry.query'`

- [ ] **Step 3: Write minimal implementation**

Create `loop_apidoc/foundry/query.py`:

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.models import Asset, Catalog, FoundryInputError

_ARTIFACT_FIELDS = {
    "openapi",
    "integration_contract",
    "provenance",
    "review",
    "validation",
    "score",
    "handoff",
}


def load_current_asset(project_root: Path, docset_id: str) -> Asset:
    pointer = store.load_current(project_root, docset_id)
    if pointer is None:
        raise FoundryInputError(f"no current asset for docset: {docset_id}")
    return store.load_asset(project_root, docset_id, pointer.current_asset)


def resolve_current_artifact(
    project_root: Path, docset_id: str, artifact: str
) -> Path:
    if artifact not in _ARTIFACT_FIELDS:
        raise FoundryInputError(f"unknown artifact: {artifact}")
    asset = load_current_asset(project_root, docset_id)
    rel = getattr(asset.artifacts, artifact)
    if rel is None:
        raise FoundryInputError(
            f"artifact not present in current asset: {artifact}"
        )
    return paths.asset_dir(project_root, docset_id, asset.asset_id) / rel


def list_docsets(project_root: Path) -> Catalog:
    return store.load_catalog(project_root)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/foundry/test_query.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/foundry/query.py tests/foundry/test_query.py
git commit -m "feat: [foundry] add read-side current-asset and artifact resolution"
```

---

### Task 8: CLI sub-app and public API exports

**Files:**
- Create: `loop_apidoc/foundry/cli.py`
- Modify: `loop_apidoc/foundry/__init__.py` (add public re-exports)
- Modify: `loop_apidoc/cli.py:8-13` (import + register the sub-app after `app` is defined)
- Test: `tests/test_cli_foundry.py`

**Interfaces:**
- Consumes: `register.register_docset`, `importer.import_run`, `approve.approve_candidate` (+ `FoundryApprovalError`), `query.list_docsets`/`load_current_asset`, `store`, `models` (`Docset`, `SourceRef`, `SourceRole`, `FoundryInputError`), `loop_apidoc.foundry.cli.foundry_app`.
- Produces: `foundry_app: typer.Typer` with commands `init`, `import`, `approve`, `list`, `current`; registered on the root app as `loop-apidoc foundry <cmd>`.

CLI surface (all commands take `--project` defaulting to `.`):
- `foundry init --docset ID --title T --provider P --product PR [--source path[:role] ...] [--scope S] [--exist-ok]`
- `foundry import --docset ID --run RUN_DIR [--overwrite]`
- `foundry approve --docset ID --run RUN_ID --by WHO [--min-score N] [--allow-failing] [--known-gap G ...] [--json]` — exit `1` on `FoundryApprovalError`, `2` on `FoundryInputError`.
- `foundry list [--json]`
- `foundry current --docset ID [--json]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_foundry.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from tests.foundry._fixtures import write_run_dir

runner = CliRunner()
_RUN_ID = "20260702T120000.000000Z"


def _init(project: Path) -> None:
    result = runner.invoke(app, [
        "foundry", "init",
        "--project", str(project),
        "--docset", "tappay-backend",
        "--title", "TapPay Backend API",
        "--provider", "tappay",
        "--product", "backend-api",
        "--source", "sources/tappay/backend.md:primary",
        "--source", "sources/tappay/errors.md:supplemental",
    ])
    assert result.exit_code == 0, result.output


def test_init_import_approve_flow(tmp_path: Path) -> None:
    _init(tmp_path)
    docset_json = tmp_path / ".foundry" / "api" / "docsets" / "tappay-backend" / "docset.json"
    assert docset_json.is_file()
    assert json.loads(docset_json.read_text())["sources"][1]["role"] == "supplemental"

    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    imp = runner.invoke(app, [
        "foundry", "import", "--project", str(tmp_path),
        "--docset", "tappay-backend", "--run", str(run_dir),
    ])
    assert imp.exit_code == 0, imp.output

    appr = runner.invoke(app, [
        "foundry", "approve", "--project", str(tmp_path),
        "--docset", "tappay-backend", "--run", _RUN_ID, "--by", "human-review", "--json",
    ])
    assert appr.exit_code == 0, appr.output
    payload = json.loads(appr.output)
    assert payload["status"] == "approved"
    assert payload["validation"]["score"] == 92

    cur = runner.invoke(app, [
        "foundry", "current", "--project", str(tmp_path), "--docset", "tappay-backend", "--json",
    ])
    assert cur.exit_code == 0, cur.output
    assert json.loads(cur.output)["current_asset"] == payload["asset_id"]


def test_approve_missing_candidate_exits_2(tmp_path: Path) -> None:
    _init(tmp_path)
    result = runner.invoke(app, [
        "foundry", "approve", "--project", str(tmp_path),
        "--docset", "tappay-backend", "--run", _RUN_ID, "--by", "a",
    ])
    assert result.exit_code == 2, result.output


def test_approve_failing_validation_exits_1(tmp_path: Path) -> None:
    _init(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID, validation_ok=False)
    runner.invoke(app, [
        "foundry", "import", "--project", str(tmp_path),
        "--docset", "tappay-backend", "--run", str(run_dir),
    ])
    result = runner.invoke(app, [
        "foundry", "approve", "--project", str(tmp_path),
        "--docset", "tappay-backend", "--run", _RUN_ID, "--by", "a",
    ])
    assert result.exit_code == 1, result.output


def test_list_shows_registered_docset(tmp_path: Path) -> None:
    _init(tmp_path)
    result = runner.invoke(app, ["foundry", "list", "--project", str(tmp_path), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["docsets"][0]["docset_id"] == "tappay-backend"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_foundry.py -v`
Expected: FAIL — `foundry` is not a registered command (typer exits non-zero with "No such command 'foundry'").

- [ ] **Step 3: Write the sub-app**

Create `loop_apidoc/foundry/cli.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

foundry_app = typer.Typer(
    help="Foundry API 專案本地資產治理（docset / candidate / asset）",
    no_args_is_help=True,
)


def _parse_source(raw: str) -> object:
    from loop_apidoc.foundry.models import SourceRef, SourceRole

    path, _, role_str = raw.partition(":")
    role = SourceRole(role_str) if role_str else SourceRole.PRIMARY
    kind = "url" if path.startswith(("http://", "https://")) else "file"
    return SourceRef(kind=kind, path=path, role=role)


@foundry_app.command("init")
def init(
    project: Path = typer.Option(Path("."), "--project", help="專案根目錄"),
    docset: str = typer.Option(..., "--docset", help="docset 識別碼"),
    title: str = typer.Option(..., "--title", help="docset 標題"),
    provider: str = typer.Option(..., "--provider", help="API 供應商"),
    product: str = typer.Option(..., "--product", help="產品/子系統名稱"),
    scope: str = typer.Option("", "--scope", help="來源範圍描述"),
    source: list[str] = typer.Option([], "--source", help="來源 path[:role]，可重複"),
    exist_ok: bool = typer.Option(False, "--exist-ok", help="docset 已存在時更新而非報錯"),
) -> None:
    """建立或更新一個 docset。"""
    from loop_apidoc.foundry.models import Docset, FoundryInputError
    from loop_apidoc.foundry.register import register_docset

    ds = Docset(
        docset_id=docset,
        title=title,
        provider=provider,
        product=product,
        source_scope=scope,
        sources=[_parse_source(s) for s in source],
    )
    try:
        result = register_docset(project, ds, exist_ok=exist_ok)
    except FoundryInputError as exc:
        typer.echo(f"foundry init input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"docset 已寫入：{result.docset_id}")


@foundry_app.command("import")
def import_(
    project: Path = typer.Option(Path("."), "--project", help="專案根目錄"),
    docset: str = typer.Option(..., "--docset", help="目標 docset 識別碼"),
    run: Path = typer.Option(..., "--run", help="已完成的 run 目錄"),
    overwrite: bool = typer.Option(False, "--overwrite", help="覆寫已存在的 candidate"),
) -> None:
    """將一個 run 目錄匯入為 candidate。"""
    from loop_apidoc.foundry.importer import import_run
    from loop_apidoc.foundry.models import FoundryInputError

    try:
        result = import_run(project, docset, run, overwrite=overwrite)
    except FoundryInputError as exc:
        typer.echo(f"foundry import input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"candidate 已匯入：{result.run_id}")


@foundry_app.command("approve")
def approve(
    project: Path = typer.Option(Path("."), "--project", help="專案根目錄"),
    docset: str = typer.Option(..., "--docset", help="docset 識別碼"),
    run: str = typer.Option(..., "--run", help="candidate 的 run id"),
    by: str = typer.Option(..., "--by", help="核准者身分或自動化閘門，如 human-review / ci-score-90"),
    min_score: Annotated[int | None, typer.Option("--min-score", min=0, max=100, help="核准所需最低分數")] = None,
    allow_failing: bool = typer.Option(False, "--allow-failing", help="即使 validation 失敗仍核准"),
    known_gap: list[str] = typer.Option([], "--known-gap", help="已知缺口，可重複"),
    json_out: bool = typer.Option(False, "--json", help="以 JSON 輸出 asset"),
) -> None:
    """將 candidate 核准為版本化 asset 並更新 current 指標。"""
    from loop_apidoc.foundry.approve import approve_candidate
    from loop_apidoc.foundry.models import FoundryApprovalError, FoundryInputError

    try:
        asset = approve_candidate(
            project, docset, run,
            approved_by=by,
            now=datetime.now(timezone.utc),
            min_score=min_score,
            allow_failing=allow_failing,
            known_gaps=list(known_gap),
        )
    except FoundryInputError as exc:
        typer.echo(f"foundry approve input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except FoundryApprovalError as exc:
        typer.echo(f"foundry approve rejected: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_out:
        typer.echo(asset.model_dump_json(indent=2))
    else:
        typer.echo(f"asset 已核准：{asset.asset_id}（current 已更新）")


@foundry_app.command("list")
def list_(
    project: Path = typer.Option(Path("."), "--project", help="專案根目錄"),
    json_out: bool = typer.Option(False, "--json", help="以 JSON 輸出目錄"),
) -> None:
    """列出所有 docset 及其 current asset。"""
    from loop_apidoc.foundry.query import list_docsets

    catalog = list_docsets(project)
    if json_out:
        typer.echo(catalog.model_dump_json(indent=2))
    else:
        for entry in catalog.docsets:
            typer.echo(f"{entry.docset_id}\t{entry.title}\tcurrent={entry.current_asset}")


@foundry_app.command("current")
def current(
    project: Path = typer.Option(Path("."), "--project", help="專案根目錄"),
    docset: str = typer.Option(..., "--docset", help="docset 識別碼"),
    json_out: bool = typer.Option(False, "--json", help="以 JSON 輸出 current 指標"),
) -> None:
    """顯示 docset 的 current 指標。"""
    from loop_apidoc.foundry import store
    from loop_apidoc.foundry.models import FoundryInputError

    pointer = store.load_current(project, docset)
    if pointer is None:
        typer.echo(f"foundry current input error: no current asset for {docset}", err=True)
        raise typer.Exit(code=2)
    if json_out:
        typer.echo(pointer.model_dump_json(indent=2))
    else:
        typer.echo(f"{pointer.current_asset}\tvalidation.ok={pointer.validation.ok}\tscore={pointer.validation.score}")
```

- [ ] **Step 4: Register the sub-app on the root CLI**

In `loop_apidoc/cli.py`, immediately after the `app = typer.Typer(...)` block (currently ending at line 18) and before the `@app.callback()` at line 21, add:

```python
from loop_apidoc.foundry.cli import foundry_app

app.add_typer(foundry_app, name="foundry")
```

- [ ] **Step 5: Add public re-exports**

Replace the contents of `loop_apidoc/foundry/__init__.py` with:

```python
"""Foundry API project-local asset governance layer."""

from loop_apidoc.foundry.approve import approve_candidate
from loop_apidoc.foundry.importer import ImportResult, import_run
from loop_apidoc.foundry.models import (
    Asset,
    AssetArtifacts,
    AssetStatus,
    AssetValidation,
    Catalog,
    CatalogDocsetEntry,
    CurrentPointer,
    Docset,
    FoundryApprovalError,
    FoundryInputError,
    SourceRef,
    SourceRole,
    make_asset_id,
)
from loop_apidoc.foundry.query import (
    list_docsets,
    load_current_asset,
    resolve_current_artifact,
)
from loop_apidoc.foundry.register import register_docset

__all__ = [
    "Asset",
    "AssetArtifacts",
    "AssetStatus",
    "AssetValidation",
    "Catalog",
    "CatalogDocsetEntry",
    "CurrentPointer",
    "Docset",
    "FoundryApprovalError",
    "FoundryInputError",
    "ImportResult",
    "SourceRef",
    "SourceRole",
    "approve_candidate",
    "import_run",
    "list_docsets",
    "load_current_asset",
    "make_asset_id",
    "register_docset",
    "resolve_current_artifact",
]
```

- [ ] **Step 6: Run the CLI test to verify it passes**

Run: `uv run pytest tests/test_cli_foundry.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: Run the whole foundry suite + lint**

Run: `uv run pytest tests/foundry tests/test_cli_foundry.py -v && uv run ruff check loop_apidoc/foundry tests/foundry tests/test_cli_foundry.py`
Expected: all tests PASS; ruff reports no errors.

- [ ] **Step 8: Commit**

```bash
git add loop_apidoc/foundry/cli.py loop_apidoc/foundry/__init__.py loop_apidoc/cli.py tests/test_cli_foundry.py
git commit -m "feat: [foundry] add CLI sub-app and public API exports"
```

---

### Task 9: Documentation

**Files:**
- Modify: `CLAUDE.md` (package boundaries table + command list)
- Modify: `docs/ARCHITECTURE.md` (add a Foundry asset-layer subsection — confirm the file exists and find the package/dataflow section first)

**Interfaces:** none (docs only).

- [ ] **Step 1: Update the package boundaries table in CLAUDE.md**

In `CLAUDE.md`, find the `| Package | Responsibility |` table (under "## Package boundaries") and add this row after the `loop_apidoc/score/` row:

```markdown
| `loop_apidoc/foundry/` | project-local asset governance under `.foundry/api/`: `models.py` (Docset/Asset/Catalog/CurrentPointer + `FoundryInputError`/`FoundryApprovalError`), `paths.py` (pure `.foundry/api/` layout), `store.py` (governance-json read/write), `register.py` (`register_docset`), `importer.py` (`import_run` → copy a completed run into `candidates/<run-id>/`, gated by the reused `diff` loader), `approve.py` (`approve_candidate` → copy candidate into a versioned `assets/<asset-id>/artifacts/`, write `asset.json`, supersede the prior asset, update `current.json`/`docset.json`/`catalog.json`), `query.py` (downstream read side: `load_current_asset`/`resolve_current_artifact`/`list_docsets`), `cli.py` (`foundry` sub-app). Assets are self-contained copies; generation is untouched. |
```

- [ ] **Step 2: Update the command list in CLAUDE.md**

In `CLAUDE.md`, find the sentence beginning "The six CLI commands are" and update it to note the Foundry sub-app. Replace the closing of that paragraph so it reads:

```markdown
The six generation/analysis CLI commands are `preprocess` (PDF→markdown), `manifest` (scan), `assemble` (assemble + validate; optional `--score`), `validate` (validate an existing run-dir), `score` (grade a completed run-dir's documentation quality), and `diff` (compare two completed run-dirs by downstream impact). A separate `foundry` sub-app (`init` / `import` / `approve` / `list` / `current`) manages the project-local `.foundry/api/` asset layer — importing completed runs as docset candidates and promoting them to approved, versioned assets with a deterministic `current` pointer.
```

- [ ] **Step 3: Update the File-I/O exits note in CLAUDE.md**

In `CLAUDE.md`, find the paragraph starting "**File-I/O exits:**" and append `foundry/` to the list of I/O-permitted modules. Change the sentence to add before the final "and `diff/report.py`":

```markdown
`foundry/store.py` (governance-json), `foundry/register.py`, `foundry/importer.py`, and `foundry/approve.py` (which copy run trees into `.foundry/`),
```

so the enumerated list of file-writing modules includes the four Foundry I/O modules alongside the existing ones.

- [ ] **Step 4: Add an architecture subsection**

Read `docs/ARCHITECTURE.md` and locate the section describing packages / data flow (search for "diff" or "score" headings). Add a new subsection after the generation/analysis flow:

```markdown
### Foundry asset layer (`.foundry/api/`)

Generation stays deterministic and untrusted-by-default: the CLI writes a run
directory, nothing more. The **Foundry** layer is a separate, explicit governance
step that turns selected runs into managed project assets:

```
output/<run-id>/
  → foundry import  → .foundry/api/docsets/<docset-id>/candidates/<run-id>/   (candidate)
  → foundry approve → .foundry/api/docsets/<docset-id>/assets/<asset-id>/     (approved, versioned)
                      + current.json (deterministic pointer for downstream)
```

- A **docset** groups the source documents that together define one API contract.
- **import** copies a completed run into `candidates/` (completeness gated by the
  reused `diff` loader).
- **approve** copies the candidate into a self-contained, immutable
  `assets/<asset-id>/artifacts/`, records `asset.json` (status, validation, score,
  source hashes, artifact paths, supersession, approval metadata), supersedes the
  previous approved asset, and updates `current.json` / `docset.json` /
  `catalog.json`.
- Downstream work (SDK authoring, CI contract checks, integration) reads the
  **current** asset via `foundry current` / `query.load_current_asset`, never an
  arbitrary run directory.

`openapi.yaml` and `integration-contract.json` remain the authoritative contract;
Foundry copies them verbatim and adds governance, never rewriting the contract.
```

- [ ] **Step 5: Verify docs mention no undefined behavior**

Run: `uv run pytest -q`
Expected: full suite PASS (confirms the doc task didn't accidentally touch code).

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md docs/ARCHITECTURE.md
git commit -m "docs: [foundry] document the .foundry/api asset governance layer"
```

---

## Self-Review

**1. Spec coverage:**

| Spec requirement | Task |
| --- | --- |
| `.foundry/api/` hidden namespace | Task 2 (paths) |
| Multiple docsets per project | Task 4 (register) + Catalog (Task 1/3) |
| Directory shape (catalog/docset/candidates/assets/current) | Tasks 2, 3, 5, 6 |
| `docset.json` model (provider/product/scope/sources/current) | Task 1 (`Docset`), Task 4 |
| `asset.json` model (status/run_id/hashes/validation/score/artifacts/supersedes/approval/gaps) | Task 1 (`Asset`), Task 6 |
| `catalog.json` project index | Task 1 (`Catalog`), Task 3 (`upsert`) |
| Run → candidate → approved → current → superseded lifecycle | Tasks 5, 6 |
| Approval checks validation + score; diff vs previous | Task 6 gate (validation+score); supersession link records the previous asset (diff-vs-previous is left to the existing `diff` command against the two asset artifact dirs — documented, not re-implemented) |
| Copy artifacts in (self-contained) | Tasks 5, 6 (`copytree`) — matches resolved Open Question 1 |
| `current.json` = id + cached metadata | Task 1 (`CurrentPointer`), Task 6 — matches resolved Open Question 2 |
| `approved_by` human **or** automated gate | Task 6 (`approved_by: str` free-form), Task 8 (`--by`) — matches resolved Open Question 3 |
| Import + approve commands | Tasks 5, 6, 8 — matches resolved Open Question 4 (full lifecycle) |
| Downstream consumes current, not raw runs | Task 7 (`query`), Task 8 (`foundry current`) |
| Generation boundary untouched | No task modifies `generate/`/`assemble.py`; Task 9 documents it |

Open Questions 1–4 were resolved with the user before planning (copy-in; id+cached metadata; free-form approver; full import+approve lifecycle). "Diff against previous approved asset" from the Lifecycle section is satisfied structurally (assets are full run copies, so the existing `diff` command runs on `assets/<id>/artifacts` directly) rather than by a new code path — this keeps DRY and is noted in Task 9's architecture text.

**2. Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N" placeholders. Every code step contains full file contents; every test step contains complete test bodies. The one explicit implementer instruction (Task 5 Step 1 note) directs confirming `Issue`/`ScoreReport` constructor fields against the real models — this is a deliberate verification step for a reused external model, not a placeholder for the Foundry code itself.

**3. Type consistency:** `Docset`, `Asset`, `AssetArtifacts`, `CurrentPointer`, `Catalog`, `CatalogDocsetEntry`, `AssetStatus`, `SourceRole`, `make_asset_id` are defined in Task 1 and used with identical signatures in Tasks 3–8. `FoundryInputError` (exit 2) vs `FoundryApprovalError` (exit 1) are used consistently. `load_run_artifacts`/`DiffInputError` reuse matches the real signatures read from `loop_apidoc/diff/loader.py`. `ImportResult` fields (`run_id`, `candidate_dir`) match between Task 5 definition and Task 8 usage. Artifact field names in `AssetArtifacts` (`integration_contract`, `handoff`, `score`, etc.) match `_build_artifacts` (Task 6), `resolve_current_artifact` `_ARTIFACT_FIELDS` (Task 7), and the CLI/tests.
