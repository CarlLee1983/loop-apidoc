"""Foundry API project-local asset governance layer.

Only value models are imported eagerly. Operational exports stay lazy so a
Foundry persistence module never has to initialise unrelated application
workflows just to reach a sibling module.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

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
    EffectiveAsset,
    EffectiveAssetArtifacts,
    EffectiveCurrentPointer,
    FeedbackCase,
    FeedbackReviewDecision,
    FoundryApprovalError,
    FoundryCurrentStaleError,
    FoundryGovernedAssetApprovalLineageError,
    FoundryGovernedAssetNotApprovedError,
    FoundryInputError,
    FoundryPublicationError,
    SourceRef,
    SourceRole,
    make_asset_id,
)


_LAZY_EXPORTS = {
    "ImportResult": ("importer", "ImportResult"),
    "approve_candidate": ("approve", "approve_candidate"),
    "approve_feedback_case": ("feedback", "approve_feedback_case"),
    "import_run": ("importer", "import_run"),
    "list_docsets": ("query", "list_docsets"),
    "load_current_asset": ("query", "load_current_asset"),
    "load_current_asset_optional": ("query", "load_current_asset_optional"),
    "load_current_effective_asset": ("query", "load_current_effective_asset"),
    "load_current_pointer": ("query", "load_current_pointer"),
    "load_governed_asset": ("query", "load_governed_asset"),
    "persist_feedback_case": ("feedback", "persist_feedback_case"),
    "read_current_artifact": ("query", "read_current_artifact"),
    "read_governed_artifact": ("query", "read_governed_artifact"),
    "record_feedback_review": ("feedback", "record_feedback_review"),
    "register_docset": ("register", "register_docset"),
    "resolve_current_artifact": ("query", "resolve_current_artifact"),
    "read_current_effective_artifact": ("query", "read_current_effective_artifact"),
    "resolve_governed_artifact": ("query", "resolve_governed_artifact"),
    "validate_governance_baseline": ("query", "validate_governance_baseline"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = import_module(f"{__name__}.{module_name}")
    value = getattr(module, attribute)
    globals()[name] = value
    return value


__all__ = [
    "Asset",
    "AssetArtifactDigests",
    "AssetArtifactKinds",
    "AssetArtifacts",
    "AssetStatus",
    "AssetValidation",
    "Catalog",
    "CatalogDocsetEntry",
    "CurrentPointer",
    "Docset",
    "EffectiveAsset",
    "EffectiveAssetArtifacts",
    "EffectiveCurrentPointer",
    "FeedbackCase",
    "FeedbackReviewDecision",
    "FoundryApprovalError",
    "FoundryCurrentStaleError",
    "FoundryGovernedAssetApprovalLineageError",
    "FoundryGovernedAssetNotApprovedError",
    "FoundryInputError",
    "FoundryPublicationError",
    "ImportResult",
    "SourceRef",
    "SourceRole",
    "approve_candidate",
    "approve_feedback_case",
    "import_run",
    "list_docsets",
    "load_current_asset",
    "load_current_asset_optional",
    "load_current_effective_asset",
    "load_current_pointer",
    "load_governed_asset",
    "make_asset_id",
    "persist_feedback_case",
    "read_current_artifact",
    "read_governed_artifact",
    "record_feedback_review",
    "register_docset",
    "resolve_current_artifact",
    "read_current_effective_artifact",
    "resolve_governed_artifact",
    "validate_governance_baseline",
]
