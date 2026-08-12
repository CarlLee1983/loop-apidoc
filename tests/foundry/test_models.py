from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from loop_apidoc.foundry.models import (
    Asset,
    AssetArtifactDigests,
    AssetArtifactKinds,
    AssetArtifacts,
    AssetStatus,
    AssetValidation,
    Catalog,
    CatalogDocsetEntry,
    CurrentPointer,
    Docset,
    FoundryApprovalError,
    FoundryInputError,
    FoundryPublicationError,
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
        schema_version="normative-asset/v1",
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
        artifact_digests=AssetArtifactDigests(
            openapi="0" * 64,
            provenance="1" * 64,
            validation="2" * 64,
        ),
        artifact_kinds=AssetArtifactKinds(
            openapi="file",
            provenance="file",
            validation="file",
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
    artifact_digests = AssetArtifactDigests(
        openapi="0" * 64,
        provenance="1" * 64,
        validation="2" * 64,
    )
    artifact_kinds = AssetArtifactKinds(
        openapi="file",
        provenance="file",
        validation="file",
    )
    pointer = CurrentPointer(
        schema_version="normative-current/v1",
        docset_id="tappay-backend",
        current_asset="tappay-backend-20260702-120000",
        asset_digest="3" * 64,
        status=AssetStatus.APPROVED,
        validation=AssetValidation(ok=True, score=92),
        generated_at="2026-07-02T12:00:00+00:00",
        artifacts=AssetArtifacts(
            openapi="artifacts/openapi.yaml",
            provenance="artifacts/provenance.json",
            validation="artifacts/validation/report.json",
        ),
        artifact_digests=artifact_digests,
        artifact_kinds=artifact_kinds,
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


def test_asset_rejects_orphaned_optional_artifact_kind() -> None:
    asset = Asset(
        schema_version="normative-asset/v1",
        asset_id="tappay-backend-20260702-120000",
        docset_id="tappay-backend",
        status=AssetStatus.APPROVED,
        run_id="20260702T120000.000000Z",
        generated_at="2026-07-02T12:00:00+00:00",
        validation=AssetValidation(ok=True),
        approved_by="fixture",
        artifacts=AssetArtifacts(
            openapi="artifacts/openapi.yaml",
            provenance="artifacts/provenance.json",
            validation="artifacts/validation/report.json",
        ),
        artifact_digests=AssetArtifactDigests(
            openapi="0" * 64,
            provenance="1" * 64,
            validation="2" * 64,
        ),
        artifact_kinds=AssetArtifactKinds(
            openapi="file",
            provenance="file",
            validation="file",
        ),
    )
    payload = asset.model_dump(mode="json")
    payload["artifact_kinds"]["review"] = "file"

    with pytest.raises(ValidationError, match="artifact path, digest, and kind"):
        Asset.model_validate(payload)


def test_approved_asset_requires_nonempty_approver() -> None:
    with pytest.raises(ValidationError, match="approved_by"):
        Asset(
            schema_version="normative-asset/v1",
            asset_id="tappay-backend-20260702-120000",
            docset_id="tappay-backend",
            status=AssetStatus.APPROVED,
            run_id="20260702T120000.000000Z",
            generated_at="2026-07-02T12:00:00+00:00",
            validation=AssetValidation(ok=True),
            artifacts=AssetArtifacts(
                openapi="artifacts/openapi.yaml",
                provenance="artifacts/provenance.json",
                validation="artifacts/validation/report.json",
            ),
            artifact_digests=AssetArtifactDigests(
                openapi="0" * 64,
                provenance="1" * 64,
                validation="2" * 64,
            ),
            artifact_kinds=AssetArtifactKinds(
                openapi="file",
                provenance="file",
                validation="file",
            ),
            approved_by=" ",
        )


def test_errors_are_value_errors() -> None:
    assert issubclass(FoundryInputError, ValueError)
    assert issubclass(FoundryApprovalError, ValueError)
    assert not issubclass(FoundryPublicationError, FoundryInputError)
