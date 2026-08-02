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


def candidate_review_dir(project_root: Path, docset_id: str, run_id: str) -> Path:
    return candidate_dir(project_root, docset_id, run_id) / "review"


def candidate_review_decision_path(
    project_root: Path, docset_id: str, run_id: str
) -> Path:
    return candidate_review_dir(project_root, docset_id, run_id) / "decision.json"


def assets_dir(project_root: Path, docset_id: str) -> Path:
    return docset_dir(project_root, docset_id) / "assets"


def asset_dir(project_root: Path, docset_id: str, asset_id: str) -> Path:
    return assets_dir(project_root, docset_id) / asset_id


def asset_manifest_path(project_root: Path, docset_id: str, asset_id: str) -> Path:
    return asset_dir(project_root, docset_id, asset_id) / "asset.json"


def asset_artifacts_dir(project_root: Path, docset_id: str, asset_id: str) -> Path:
    return asset_dir(project_root, docset_id, asset_id) / "artifacts"


def feedback_cases_dir(project_root: Path, docset_id: str) -> Path:
    return docset_dir(project_root, docset_id) / "feedback" / "cases"


def feedback_case_dir(project_root: Path, docset_id: str, case_id: str) -> Path:
    return feedback_cases_dir(project_root, docset_id) / case_id


def feedback_case_manifest_path(
    project_root: Path, docset_id: str, case_id: str
) -> Path:
    return feedback_case_dir(project_root, docset_id, case_id) / "case.json"


def effective_scopes_dir(project_root: Path, docset_id: str) -> Path:
    return docset_dir(project_root, docset_id) / "effective" / "scopes"


def effective_scope_dir(project_root: Path, docset_id: str, scope_digest: str) -> Path:
    return effective_scopes_dir(project_root, docset_id) / scope_digest


def effective_assets_dir(project_root: Path, docset_id: str, scope_digest: str) -> Path:
    return effective_scope_dir(project_root, docset_id, scope_digest) / "assets"


def effective_asset_dir(
    project_root: Path, docset_id: str, scope_digest: str, asset_id: str
) -> Path:
    return effective_assets_dir(project_root, docset_id, scope_digest) / asset_id


def effective_asset_manifest_path(
    project_root: Path, docset_id: str, scope_digest: str, asset_id: str
) -> Path:
    return (
        effective_asset_dir(project_root, docset_id, scope_digest, asset_id)
        / "asset.json"
    )


def effective_asset_artifacts_dir(
    project_root: Path, docset_id: str, scope_digest: str, asset_id: str
) -> Path:
    return (
        effective_asset_dir(project_root, docset_id, scope_digest, asset_id)
        / "artifacts"
    )


def effective_current_path(
    project_root: Path, docset_id: str, scope_digest: str
) -> Path:
    return effective_scope_dir(project_root, docset_id, scope_digest) / "current.json"
