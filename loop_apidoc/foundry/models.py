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
