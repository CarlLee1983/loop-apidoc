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
