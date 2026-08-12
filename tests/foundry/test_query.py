from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.core.conformance import canonical_digest
from loop_apidoc.foundry import approve, importer, paths, query, register, store
from loop_apidoc.foundry.models import (
    Docset,
    FoundryGovernedAssetApprovalLineageError,
    FoundryInputError,
)
from tests.foundry._fixtures import write_run_dir

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
_RUN_ID = "20260702T120000.000000Z"


def _approve(tmp_path: Path, **run_kwargs: object) -> str:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )
    importer.import_run(
        tmp_path,
        "tappay-backend",
        write_run_dir(tmp_path / "output" / _RUN_ID, **run_kwargs),  # type: ignore[arg-type]
    )
    return approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    ).asset_id


def test_load_current_asset_returns_approved(tmp_path: Path) -> None:
    asset_id = _approve(tmp_path)
    asset = query.load_current_asset(tmp_path, "tappay-backend")
    assert asset.asset_id == asset_id
    assert asset.validation.score == 92


def test_load_current_asset_rejects_unknown_pointer_fields(tmp_path: Path) -> None:
    _approve(tmp_path)
    pointer_path = paths.current_path(tmp_path, "tappay-backend")
    payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    payload["unexpected"] = "tampered"
    pointer_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FoundryInputError, match="current.json is invalid"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_load_current_asset_rejects_unversioned_pointer(tmp_path: Path) -> None:
    _approve(tmp_path)
    pointer_path = paths.current_path(tmp_path, "tappay-backend")
    payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    payload.pop("schema_version")
    pointer_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FoundryInputError, match="current.json is invalid"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_load_current_asset_rejects_tampered_asset_metadata(tmp_path: Path) -> None:
    asset_id = _approve(tmp_path)
    asset_path = paths.asset_manifest_path(tmp_path, "tappay-backend", asset_id)
    payload = json.loads(asset_path.read_text(encoding="utf-8"))
    payload["approved_by"] = "attacker"
    asset_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FoundryInputError, match="current asset digest is stale"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_load_current_asset_rejects_missing_approver_lineage(tmp_path: Path) -> None:
    asset_id = _approve(tmp_path)
    asset = store.load_asset(tmp_path, "tappay-backend", asset_id)
    tampered = asset.model_copy(update={"approved_by": ""})
    store.save_asset(tmp_path, tampered)
    pointer = store.load_current(tmp_path, "tappay-backend")
    assert pointer is not None
    store.save_current(
        tmp_path,
        "tappay-backend",
        pointer.model_copy(update={"asset_digest": canonical_digest(tampered)}),
    )

    with pytest.raises(FoundryInputError):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_load_current_asset_rejects_pointer_summary_tampering(tmp_path: Path) -> None:
    _approve(tmp_path)
    pointer_path = paths.current_path(tmp_path, "tappay-backend")
    payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    payload["validation"]["score"] = 0
    pointer_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FoundryInputError, match="current pointer summary is stale"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_load_current_asset_rejects_docset_head_drift(tmp_path: Path) -> None:
    _approve(tmp_path)
    docset = store.load_docset(tmp_path, "tappay-backend")
    store.save_docset(tmp_path, docset.model_copy(update={"current_asset": "other"}))

    with pytest.raises(FoundryInputError, match="current docset head is stale"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_load_current_asset_rejects_catalog_head_drift(tmp_path: Path) -> None:
    _approve(tmp_path)
    catalog = store.load_catalog(tmp_path)
    entry = catalog.docsets[0]
    store.save_catalog(
        tmp_path,
        catalog.model_copy(
            update={
                "docsets": [entry.model_copy(update={"current_asset": "other"})]
            }
        ),
    )

    with pytest.raises(FoundryInputError, match="current catalog head is stale"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_load_current_asset_rejects_duplicate_catalog_heads(tmp_path: Path) -> None:
    _approve(tmp_path)
    catalog = store.load_catalog(tmp_path)
    store.save_catalog(tmp_path, catalog.model_copy(update={"docsets": catalog.docsets * 2}))

    with pytest.raises(FoundryInputError, match="current catalog entry is not unique"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_load_current_asset_rejects_catalog_summary_drift(tmp_path: Path) -> None:
    _approve(tmp_path)
    catalog = store.load_catalog(tmp_path)
    entry = catalog.docsets[0]
    store.save_catalog(
        tmp_path,
        catalog.model_copy(
            update={
                "docsets": [entry.model_copy(update={"provider": "attacker"})]
            }
        ),
    )

    with pytest.raises(FoundryInputError, match="current catalog summary is stale"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_load_current_asset_rejects_symlinked_current_manifest(tmp_path: Path) -> None:
    _approve(tmp_path)
    pointer_path = paths.current_path(tmp_path, "tappay-backend")
    outside = tmp_path / "outside-current.json"
    outside.write_bytes(pointer_path.read_bytes())
    pointer_path.unlink()
    pointer_path.symlink_to(outside)

    with pytest.raises(FoundryInputError, match="current.json path is unsafe"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_load_current_asset_without_pointer_raises(tmp_path: Path) -> None:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )
    with pytest.raises(FoundryInputError, match="no current asset"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_load_current_asset_optional_rejects_unsafe_docset_id(tmp_path: Path) -> None:
    with pytest.raises(FoundryInputError, match="unsafe docset id"):
        query.load_current_asset_optional(tmp_path, "../escape")


def test_load_current_asset_optional_rejects_current_directory(tmp_path: Path) -> None:
    register.register_docset(
        tmp_path,
        Docset(
            docset_id="tappay-backend",
            title="T",
            provider="tappay",
            product="backend-api",
        ),
    )
    paths.current_path(tmp_path, "tappay-backend").mkdir(parents=True)

    with pytest.raises(FoundryInputError, match="current.json path is unsafe"):
        query.load_current_asset_optional(tmp_path, "tappay-backend")


def test_load_current_asset_optional_rejects_dangling_current_symlink(tmp_path: Path) -> None:
    register.register_docset(
        tmp_path,
        Docset(
            docset_id="tappay-backend",
            title="T",
            provider="tappay",
            product="backend-api",
        ),
    )
    current_path = paths.current_path(tmp_path, "tappay-backend")
    current_path.parent.mkdir(parents=True, exist_ok=True)
    current_path.symlink_to(tmp_path / "missing-current.json")

    with pytest.raises(FoundryInputError, match="current.json path is unsafe"):
        query.load_current_asset_optional(tmp_path, "tappay-backend")


def test_load_current_asset_optional_rejects_absent_pointer_with_governed_heads(
    tmp_path: Path,
) -> None:
    register.register_docset(
        tmp_path,
        Docset(
            docset_id="tappay-backend",
            title="T",
            provider="tappay",
            product="backend-api",
            current_asset="old-asset",
        ),
    )

    with pytest.raises(FoundryInputError, match="current pointer is missing"):
        query.load_current_asset_optional(tmp_path, "tappay-backend")


def test_load_current_asset_optional_rejects_missing_docset(tmp_path: Path) -> None:
    with pytest.raises(FoundryInputError, match="docset.json"):
        query.load_current_asset_optional(tmp_path, "tappay-backend")


def test_load_current_asset_optional_rejects_malformed_docset(tmp_path: Path) -> None:
    register.register_docset(
        tmp_path,
        Docset(
            docset_id="tappay-backend",
            title="T",
            provider="tappay",
            product="backend-api",
        ),
    )
    paths.docset_manifest_path(tmp_path, "tappay-backend").write_text(
        "{not-json", encoding="utf-8"
    )

    with pytest.raises(FoundryInputError, match="docset.json"):
        query.load_current_asset_optional(tmp_path, "tappay-backend")


def test_load_current_asset_optional_rejects_duplicate_null_catalog_heads(
    tmp_path: Path,
) -> None:
    register.register_docset(
        tmp_path,
        Docset(
            docset_id="tappay-backend",
            title="T",
            provider="tappay",
            product="backend-api",
        ),
    )
    catalog = store.load_catalog(tmp_path)
    entry = catalog.docsets[0]
    store.save_catalog(
        tmp_path,
        catalog.model_copy(update={"docsets": [entry, entry.model_copy()]}),
    )

    with pytest.raises(FoundryInputError, match="catalog entry is not unique"):
        query.load_current_asset_optional(tmp_path, "tappay-backend")


def test_resolve_current_artifact_returns_existing_path(tmp_path: Path) -> None:
    asset_id = _approve(tmp_path)
    openapi = query.resolve_current_artifact(tmp_path, "tappay-backend", "openapi")
    assert openapi.is_file()
    assert openapi.name == "openapi.yaml"
    assert asset_id in str(openapi)

    handoff = query.resolve_current_artifact(tmp_path, "tappay-backend", "handoff")
    assert handoff.is_dir()


def test_resolve_current_artifact_rejects_tampered_bytes(tmp_path: Path) -> None:
    _approve(tmp_path)
    openapi = paths.asset_artifacts_dir(
        tmp_path, "tappay-backend", query.load_current_asset(tmp_path, "tappay-backend").asset_id
    ) / "openapi.yaml"
    openapi.write_text("tampered", encoding="utf-8")

    with pytest.raises(FoundryInputError, match="artifact digest is stale"):
        query.resolve_current_artifact(tmp_path, "tappay-backend", "openapi")


def test_read_governed_artifact_returns_digest_verified_bytes(tmp_path: Path) -> None:
    asset_id = _approve(tmp_path)
    path = query.resolve_governed_artifact(
        tmp_path, "tappay-backend", asset_id, "openapi"
    )
    path.write_text("tampered", encoding="utf-8")

    with pytest.raises(FoundryInputError, match="artifact digest is stale"):
        query.read_governed_artifact(tmp_path, "tappay-backend", asset_id, "openapi")


def test_resolve_current_artifact_unknown_name_raises(tmp_path: Path) -> None:
    _approve(tmp_path)
    with pytest.raises(FoundryInputError, match="unknown artifact"):
        query.resolve_current_artifact(tmp_path, "tappay-backend", "bogus")


def test_resolve_current_artifact_absent_field_raises(tmp_path: Path) -> None:
    _approve(tmp_path, with_integration=False)
    with pytest.raises(FoundryInputError, match="not present"):
        query.resolve_current_artifact(tmp_path, "tappay-backend", "integration_contract")


def test_load_governed_asset_reports_missing_approval_lineage_with_a_typed_error(
    tmp_path: Path,
) -> None:
    asset_id = _approve(tmp_path)
    asset = store.load_asset(tmp_path, "tappay-backend", asset_id)
    store.save_asset(tmp_path, asset.model_copy(update={"approved_by": ""}))

    with pytest.raises(FoundryGovernedAssetApprovalLineageError):
        query.load_governed_asset(tmp_path, "tappay-backend", asset_id)


def test_resolve_current_artifact_rejects_symlinked_asset_root(tmp_path: Path) -> None:
    _approve(tmp_path)
    assets_root = paths.assets_dir(tmp_path, "tappay-backend")
    real_root = assets_root.with_name("assets-real")
    assets_root.rename(real_root)
    assets_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(FoundryInputError, match="unsafe artifact path"):
        query.resolve_current_artifact(tmp_path, "tappay-backend", "openapi")


@pytest.mark.parametrize("relative", ("/tmp/outside.yaml", "artifacts/../outside.yaml"))
def test_resolve_current_artifact_rejects_absolute_or_traversal_path(
    tmp_path: Path, relative: str
) -> None:
    asset_id = _approve(tmp_path)
    asset = store.load_asset(tmp_path, "tappay-backend", asset_id)
    updated = asset.model_copy(
        update={
            "artifacts": asset.artifacts.model_copy(update={"openapi": relative})
        }
    )
    store.save_asset(tmp_path, updated)
    pointer = store.load_current(tmp_path, "tappay-backend")
    assert pointer is not None
    store.save_current(
        tmp_path,
        "tappay-backend",
        pointer.model_copy(
            update={
                "asset_digest": canonical_digest(updated),
                "artifacts": updated.artifacts,
            }
        ),
    )

    with pytest.raises(FoundryInputError, match="unsafe artifact path"):
        query.resolve_current_artifact(tmp_path, "tappay-backend", "openapi")


def test_resolve_current_artifact_rejects_symlinked_file(tmp_path: Path) -> None:
    asset_id = _approve(tmp_path)
    openapi = paths.asset_artifacts_dir(tmp_path, "tappay-backend", asset_id) / "openapi.yaml"
    outside = tmp_path / "outside.yaml"
    outside.write_text("outside", encoding="utf-8")
    openapi.unlink()
    openapi.symlink_to(outside)

    with pytest.raises(FoundryInputError, match="unsafe artifact path"):
        query.resolve_current_artifact(tmp_path, "tappay-backend", "openapi")


def test_list_docsets_returns_catalog(tmp_path: Path) -> None:
    _approve(tmp_path)
    catalog = query.list_docsets(tmp_path)
    assert [d.docset_id for d in catalog.docsets] == ["tappay-backend"]
    assert catalog.docsets[0].current_asset is not None
