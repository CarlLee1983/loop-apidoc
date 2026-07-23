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
