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
    ReviewSummary,
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
        review_decision=rel("review", "decision.json"),
    )


def approve_candidate(
    project_root: Path,
    docset_id: str,
    run_id: str,
    *,
    now: datetime,
    approved_by: str | None = None,
    min_score: int | None = None,
    allow_failing: bool = False,
    known_gaps: list[str] | None = None,
    review: ReviewSummary | None = None,
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
        review=review or ReviewSummary(),
    )

    store.save_asset(project_root, asset)
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

    if docset.current_asset:
        prior = store.load_asset(project_root, docset_id, docset.current_asset)
        store.save_asset(
            project_root, prior.model_copy(update={"status": AssetStatus.SUPERSEDED})
        )

    # This is the externally consumed promotion signal. All remaining writes happen
    # before it so any earlier failure leaves the existing current pointer intact.
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
            review=asset.review,
        ),
    )

    return asset
