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
