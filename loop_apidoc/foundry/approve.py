from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NoReturn

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from loop_apidoc.core.conformance import canonical_digest
from loop_apidoc.core.governance import approve_release
from loop_apidoc.core.models import Actor, ActorKind, ApprovalDecision
from loop_apidoc.diff.loader import DiffInputError, load_run_artifacts
from loop_apidoc.foundry.strict_artifacts import (
    StrictCoreExecutionError,
    require_eligible_strict_candidate,
)
from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.integrity import digest_artifact
from loop_apidoc.foundry.query import load_current_asset, validate_governance_baseline
from loop_apidoc.foundry.models import (
    Asset,
    AssetArtifactDigests,
    AssetArtifactKinds,
    AssetArtifacts,
    AssetStatus,
    AssetValidation,
    CatalogDocsetEntry,
    CurrentPointer,
    FoundryApprovalError,
    FoundryInputError,
    FoundryPublicationError,
    ReviewSummary,
    make_asset_id,
)


class _LegacyAsset(BaseModel):
    """Read-only shape accepted only by the explicit legacy re-approval path."""

    model_config = ConfigDict(extra="forbid")

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
    review: ReviewSummary = Field(default_factory=ReviewSummary)


class _LegacyCurrentPointer(BaseModel):
    """Read-only shape accepted only by the explicit legacy re-approval path."""

    model_config = ConfigDict(extra="forbid")

    current_asset: str
    status: AssetStatus
    validation: AssetValidation
    generated_at: str
    approved_at: str | None = None
    artifacts: AssetArtifacts
    review: ReviewSummary = Field(default_factory=ReviewSummary)


@dataclass(frozen=True)
class _LegacyCapture:
    raw: bytes
    digest: str


@dataclass
class _ApprovalTransactionState:
    governance_snapshot: list[tuple[int, str, str, bytes | None]] | None = None
    staging_root: Path | None = None
    asset_root: Path | None = None
    published_asset_root: bool = False
    staging_identity: tuple[int, int] | None = None
    published_identity: tuple[int, int] | None = None
    recovery_required: bool = False


def _verify_candidate_binding(
    candidate_dir: Path, expected_digests: dict[str, str]
) -> None:
    """Verify the exact candidate artifact set bound by the review decision."""
    from loop_apidoc.review.binding import (
        approval_artifact_digests,
        artifact_digests,
    )

    try:
        reviewed_digests = artifact_digests(candidate_dir)
        actual_digests = (
            approval_artifact_digests(candidate_dir, reviewed_digests)
            if "review/decision.json" in expected_digests
            else reviewed_digests
        )
    except ValueError as exc:
        raise FoundryInputError(str(exc)) from exc
    if actual_digests.keys() != expected_digests.keys():
        raise FoundryInputError("review candidate artifact set is stale")
    for relative, expected in expected_digests.items():
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise FoundryInputError(f"review candidate artifact path is unsafe: {relative}")
        target = candidate_dir / relative_path
        try:
            target.relative_to(candidate_dir)
        except ValueError as exc:
            raise FoundryInputError(f"review candidate artifact path is unsafe: {relative}") from exc
        actual = actual_digests[relative]
        if actual != expected:
            raise FoundryInputError(f"review candidate artifact digest is stale: {relative}")


def _capture_legacy_record(
    path: Path, expected: str | None, label: str
) -> _LegacyCapture:
    if expected is None or len(expected) != 64 or any(
        character not in "0123456789abcdef" for character in expected
    ):
        raise FoundryInputError(f"legacy {label} requires a trusted digest")
    if path.is_symlink() or not path.is_file():
        raise FoundryInputError(f"legacy {label} is missing or unsafe")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FoundryInputError(f"legacy {label} cannot be read") from exc
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise FoundryInputError(f"legacy {label} trusted digest mismatch")
    return _LegacyCapture(raw=raw, digest=actual)


def _parse_legacy_model(
    capture: _LegacyCapture, model: type[BaseModel], label: str
) -> BaseModel:
    try:
        payload = json.loads(capture.raw)
    except ValueError as exc:
        raise FoundryInputError(f"legacy {label} is invalid") from exc
    if not isinstance(payload, dict):
        raise FoundryInputError(f"legacy {label} is invalid")
    version = payload.get("schema_version")
    if version is not None:
        if not isinstance(version, str):
            raise FoundryInputError(f"legacy {label} has an invalid schema version")
        raise FoundryInputError(
            f"legacy re-approval requires an unversioned {label}"
        )
    try:
        return model.model_validate_json(capture.raw)
    except (ValidationError, ValueError) as exc:
        raise FoundryInputError(f"legacy {label} is invalid") from exc


def _load_legacy_current(
    project_root: Path,
    docset_id: str,
    expected_asset_id: str,
    *,
    current_sha256: str | None,
    asset_sha256: str | None,
) -> tuple[_LegacyAsset, _LegacyCapture]:
    if (
        not expected_asset_id
        or expected_asset_id in {".", ".."}
        or "/" in expected_asset_id
        or "\\" in expected_asset_id
    ):
        raise FoundryInputError("legacy current asset id is unsafe")
    pointer_path = paths.current_path(project_root, docset_id)
    asset_path = paths.asset_manifest_path(project_root, docset_id, expected_asset_id)
    # Capture both immutable byte buffers before parsing either record.  The
    # digest and model below are always derived from these exact buffers.
    pointer_capture = _capture_legacy_record(
        pointer_path, current_sha256, "current.json"
    )
    asset_capture = _capture_legacy_record(asset_path, asset_sha256, "asset.json")
    pointer = _parse_legacy_model(
        pointer_capture, _LegacyCurrentPointer, "current pointer"
    )
    assert isinstance(pointer, _LegacyCurrentPointer)
    if pointer.current_asset != expected_asset_id:
        raise FoundryInputError("legacy current pointer identity is stale")
    if pointer.status is not AssetStatus.APPROVED:
        raise FoundryInputError("legacy current asset is not approved")
    asset = _parse_legacy_model(
        asset_capture, _LegacyAsset, "asset manifest"
    )
    assert isinstance(asset, _LegacyAsset)
    if asset.asset_id != expected_asset_id or asset.docset_id != docset_id:
        raise FoundryInputError("legacy current asset identity is stale")
    if asset.status is not AssetStatus.APPROVED:
        raise FoundryInputError("legacy current asset is not approved")
    for field in (
        "status",
        "validation",
        "generated_at",
        "approved_at",
        "artifacts",
        "review",
    ):
        if getattr(pointer, field) != getattr(asset, field):
            raise FoundryInputError("legacy current pointer summary is stale")
    docset = validate_governance_baseline(project_root, docset_id)
    if docset.current_asset != expected_asset_id:
        raise FoundryInputError("legacy docset current asset is stale")
    matching_entries = [
        entry
        for entry in store.load_catalog(project_root).docsets
        if entry.docset_id == docset_id
    ]
    if len(matching_entries) != 1:
        raise FoundryInputError("legacy catalog entry is not unique")
    catalog_entry = matching_entries[0]
    if catalog_entry.current_asset != expected_asset_id:
        raise FoundryInputError("legacy catalog current asset is stale")
    if (
        catalog_entry.title != docset.title
        or catalog_entry.provider != docset.provider
        or catalog_entry.product != docset.product
    ):
        raise FoundryInputError("legacy catalog summary is stale")
    return asset, pointer_capture


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


def _governance_snapshot(
    *,
    docset_parent_fd: int,
    api_parent_fd: int,
    current_bytes: bytes | None = None,
) -> list[tuple[int, str, str, bytes | None]]:
    return [
        (
            docset_parent_fd,
            "current.json",
            "current.json",
            current_bytes
            if current_bytes is not None
            else store.read_head_relative(docset_parent_fd, "current.json"),
        ),
        (
            docset_parent_fd,
            "docset.json",
            "docset.json",
            store.read_head_relative(docset_parent_fd, "docset.json"),
        ),
        (
            api_parent_fd,
            "catalog.json",
            "catalog.json",
            store.read_head_relative(api_parent_fd, "catalog.json"),
        ),
    ]


def _restore_governance_snapshot(
    snapshot: list[tuple[int, str, str, bytes | None]],
) -> list[tuple[str, BaseException]]:
    failures: list[tuple[str, BaseException]] = []
    for parent_fd, name, label, content in snapshot:
        try:
            store.restore_head_relative(parent_fd, name, content)
        except BaseException as exc:
            failures.append((label, exc))
    return failures


def _cleanup_approval_outputs(
    staging_root: Path | None,
    asset_root: Path,
    *,
    published_asset_root: bool,
    assets_parent_fd: int,
    staging_identity: tuple[int, int] | None,
    published_identity: tuple[int, int] | None,
) -> list[tuple[str, BaseException]]:
    failures: list[tuple[str, BaseException]] = []
    targets: list[tuple[str, Path, tuple[int, int]]] = []
    if staging_root is not None and staging_identity is not None:
        targets.append(("staged asset root", staging_root, staging_identity))
    if published_asset_root and published_identity is not None:
        targets.append(("asset root", asset_root, published_identity))
    for label, path, identity in targets:
        try:
            store.remove_owned_entry_relative(assets_parent_fd, path.name, identity)
        except BaseException as exc:
            failures.append((label, exc))
    return failures


def _raise_approval_failure(
    primary: BaseException,
    snapshot: list[tuple[int, str, str, bytes | None]],
    staging_root: Path | None,
    asset_root: Path,
    *,
    published_asset_root: bool,
    assets_parent_fd: int,
    state: _ApprovalTransactionState,
) -> NoReturn:
    rollback_failures = _restore_governance_snapshot(snapshot)
    cleanup_failures = (
        []
        if rollback_failures
        else _cleanup_approval_outputs(
            staging_root,
            asset_root,
            published_asset_root=published_asset_root,
            assets_parent_fd=assets_parent_fd,
            staging_identity=state.staging_identity,
            published_identity=state.published_identity,
        )
    )
    failures = rollback_failures + cleanup_failures
    if failures:
        state.recovery_required = True
        details = "; ".join(
            f"{label}: {type(error).__name__}: {error}"
            for label, error in failures
        )
        raise FoundryPublicationError(
            f"approval failed: {primary}; rollback/cleanup failures: {details}"
        ) from primary
    raise primary


def _build_artifacts(
    artifacts_dir: Path,
) -> tuple[AssetArtifacts, AssetArtifactDigests, AssetArtifactKinds]:
    def rel(*parts: str) -> str | None:
        return "artifacts/" + "/".join(parts) if artifacts_dir.joinpath(*parts).exists() else None

    handoff = "artifacts/handoff/" if (artifacts_dir / "handoff").is_dir() else None
    artifacts = AssetArtifacts(
        openapi="artifacts/openapi.yaml",
        provenance="artifacts/provenance.json",
        validation="artifacts/validation/report.json",
        manifest=rel("manifest.json"),
        integration_contract=rel("integration-contract.json"),
        preparation=rel("preparation-report.json"),
        review=rel("review.html"),
        score=rel("score", "score.json"),
        handoff=handoff,
        review_decision=rel("review", "decision.json"),
        run_descriptor=rel("run.json"),
        core_execution=rel("core", "execution.json"),
        core_release=rel("core", "release.json"),
        core_contract=rel("core", "contract.json"),
        core_decision=rel("core", "decision.json"),
        core_evidence=rel("core", "evidence.json"),
        core_claims=rel("core", "claims.json"),
        core_relationships=rel("core", "relationships.json"),
    )
    digests: dict[str, str | None] = {}
    kinds: dict[str, str | None] = {}
    for name in AssetArtifacts.model_fields:
        relative = getattr(artifacts, name)
        if relative is None:
            digests[name] = None
            kinds[name] = None
            continue
        target = artifacts_dir.parent / relative
        kind = "tree" if target.is_dir() else "file" if target.is_file() else None
        if kind is None:
            raise FoundryApprovalError(f"asset artifact is missing: {name}")
        expected_kind = "tree" if name == "handoff" else "file"
        if kind != expected_kind:
            raise FoundryApprovalError(
                f"asset artifact has the wrong kind: {name}"
            )
        kinds[name] = kind
        digests[name] = digest_artifact(target, kind, name)
    return (
        artifacts,
        AssetArtifactDigests(**digests),
        AssetArtifactKinds(**kinds),
    )


def _approve_candidate_locked(
    project_root: Path,
    docset_id: str,
    run_id: str,
    *,
    now: datetime,
    approved_by: str | None = None,
    min_score: int | None = None,
    allow_failing: bool = False,
    reapprove_legacy: bool = False,
    legacy_current_sha256: str | None = None,
    legacy_asset_sha256: str | None = None,
    known_gaps: list[str] | None = None,
    review: ReviewSummary | None = None,
    expected_base_asset_id: str | None = None,
    expected_base_asset_digest: str | None = None,
    enforce_expected_base: bool = False,
    expected_candidate_artifact_digests: dict[str, str] | None = None,
    assets_parent_fd: int | None = None,
    docset_parent_fd: int | None = None,
    api_parent_fd: int | None = None,
    _state: _ApprovalTransactionState | None = None,
) -> Asset:
    state = _state or _ApprovalTransactionState()
    if not approved_by or not approved_by.strip():
        raise FoundryApprovalError("normative approval requires a named approver")
    if (legacy_current_sha256 is not None or legacy_asset_sha256 is not None) and not reapprove_legacy:
        raise FoundryInputError("legacy trusted bindings require --reapprove-legacy")
    docset = validate_governance_baseline(project_root, docset_id)

    candidate = paths.candidate_dir(project_root, docset_id, run_id)
    if not candidate.is_dir():
        raise FoundryInputError(f"candidate not found: {run_id}")

    try:
        run = load_run_artifacts(candidate)
    except DiffInputError as exc:
        raise FoundryInputError(f"candidate is not a valid run: {exc}") from exc
    try:
        strict_release = require_eligible_strict_candidate(candidate)
    except StrictCoreExecutionError as exc:
        raise FoundryApprovalError(str(exc)) from exc
    if strict_release is not None and not approved_by:
        raise FoundryApprovalError("strict Core approval requires a named approver")

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

    previous_asset = None
    previous_asset_id: str | None = None
    legacy_current_capture: _LegacyCapture | None = None
    if reapprove_legacy and docset.current_asset is None:
        raise FoundryInputError("legacy re-approval requires an existing current asset")
    if docset.current_asset is not None:
        if reapprove_legacy:
            legacy_asset, legacy_current_capture = _load_legacy_current(
                project_root,
                docset_id,
                docset.current_asset,
                current_sha256=legacy_current_sha256,
                asset_sha256=legacy_asset_sha256,
            )
            previous_asset_id = legacy_asset.asset_id
        else:
            previous_asset = load_current_asset(project_root, docset_id)
            if previous_asset.asset_id != docset.current_asset:
                raise FoundryInputError("docset current asset is stale")
            previous_asset_id = previous_asset.asset_id

    if enforce_expected_base:
        if previous_asset_id != expected_base_asset_id:
            raise FoundryInputError("reviewed predecessor is stale")
        if previous_asset is not None and expected_base_asset_digest is not None:
            if canonical_digest(previous_asset) != expected_base_asset_digest:
                raise FoundryInputError("reviewed predecessor digest is stale")

    asset_id = make_asset_id(docset_id, now)
    asset_root = paths.asset_dir(project_root, docset_id, asset_id)
    state.asset_root = asset_root
    if asset_root.exists() or asset_root.is_symlink():
        raise FoundryApprovalError(f"asset already exists: {asset_id}")
    if assets_parent_fd is None or docset_parent_fd is None or api_parent_fd is None:
        raise FoundryInputError("approval transaction descriptors are required")
    governance_snapshot = _governance_snapshot(
        docset_parent_fd=docset_parent_fd,
        api_parent_fd=api_parent_fd,
        current_bytes=(
            legacy_current_capture.raw if legacy_current_capture is not None else None
        ),
    )
    state.governance_snapshot = governance_snapshot
    staging_root: Path | None = None
    staging_fd = -1
    publication = store.AssetPublication()
    try:
        store.validate_governance_namespace(
            project_root,
            docset_id,
            api_fd=api_parent_fd,
            docset_fd=docset_parent_fd,
            assets_fd=assets_parent_fd,
        )
        staging_name, staging_fd, staging_identity = (
            store.create_owned_directory_relative(
                assets_parent_fd, prefix=f".{asset_id}-"
            )
        )
        staging_root = store.directory_fd_path(staging_fd)
        state.staging_root = staging_root
        state.staging_identity = staging_identity
        artifacts_dir = staging_root / "artifacts"
        if expected_candidate_artifact_digests is not None:
            _verify_candidate_binding(candidate, expected_candidate_artifact_digests)
        pinned_candidate = (
            store.directory_fd_path(docset_parent_fd) / "candidates" / run_id
        )
        store.copy_tree_to_directory(pinned_candidate, staging_fd, "artifacts")
        if expected_candidate_artifact_digests is not None:
            _verify_candidate_binding(artifacts_dir, expected_candidate_artifact_digests)
        if strict_release is not None:
            try:
                copied_strict_release = require_eligible_strict_candidate(artifacts_dir)
            except StrictCoreExecutionError as exc:
                raise FoundryApprovalError(str(exc)) from exc
            if copied_strict_release is None:
                raise FoundryApprovalError(
                    "copied strict Core execution is not eligible"
                )
            strict_release = copied_strict_release
            try:
                approved_release = approve_release(
                    strict_release,
                    ApprovalDecision(
                        approved=True,
                        actor=Actor(id=approved_by, kind=ActorKind.APPROVER),
                        decided_at=now,
                        reason="Foundry human approval",
                    ),
                )
            except ValueError as exc:
                raise FoundryApprovalError(str(exc)) from exc
            store.write_model_relative(
                staging_fd, "artifacts/core/release.json", approved_release
            )

        source_hashes = [src.sha256 for src in run.manifest.local_sources]
        artifacts, artifact_digests, artifact_kinds = _build_artifacts(artifacts_dir)
        asset = Asset(
            schema_version="normative-asset/v1",
            asset_id=asset_id,
            docset_id=docset_id,
            status=AssetStatus.APPROVED,
            run_id=run_id,
            generated_at=run.manifest.generated_at.isoformat(),
            source_hashes=source_hashes,
            validation=AssetValidation(ok=validation_ok, score=score),
            artifacts=artifacts,
            artifact_digests=artifact_digests,
            artifact_kinds=artifact_kinds,
            supersedes=previous_asset_id,
            approved_at=now.isoformat(),
            approved_by=approved_by,
            known_gaps=list(known_gaps or []),
            review=review or ReviewSummary(),
        )

        pointer = CurrentPointer(
            schema_version="normative-current/v1",
            docset_id=docset_id,
            current_asset=asset.asset_id,
            asset_digest=canonical_digest(asset),
            status=asset.status,
            validation=asset.validation,
            generated_at=asset.generated_at,
            approved_at=asset.approved_at,
            artifacts=asset.artifacts,
            artifact_digests=asset.artifact_digests,
            artifact_kinds=asset.artifact_kinds,
            review=asset.review,
        )
        store.write_model_relative(staging_fd, "asset.json", asset)
        store.publish_asset(
            Path(staging_name),
            asset_root,
            outcome=publication,
            parent_fd=assets_parent_fd,
            expected_identity=staging_identity,
        )
        state.published_asset_root = publication.owned_root
        state.published_identity = publication.identity
        updated_docset = docset.model_copy(update={"current_asset": asset.asset_id})
        store.save_docset(
            project_root, updated_docset, parent_fd=docset_parent_fd
        )
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
            parent_fd=api_parent_fd,
        )

        # This is the externally consumed promotion signal. Publish it last.
        store.save_current(
            project_root, docset_id, pointer, parent_fd=docset_parent_fd
        )
        store.validate_governance_namespace(
            project_root,
            docset_id,
            api_fd=api_parent_fd,
            docset_fd=docset_parent_fd,
            assets_fd=assets_parent_fd,
        )
    except ValidationError as exc:
        state.published_asset_root = publication.owned_root
        state.published_identity = publication.identity
        _raise_approval_failure(
            FoundryApprovalError(str(exc)),
            governance_snapshot,
            staging_root,
            asset_root,
            published_asset_root=publication.owned_root,
            assets_parent_fd=assets_parent_fd,
            state=state,
        )
    except BaseException as exc:
        if getattr(exc, "recovery_required", False):
            state.recovery_required = True
        state.published_asset_root = publication.owned_root
        state.published_identity = publication.identity
        _raise_approval_failure(
            exc,
            governance_snapshot,
            staging_root,
            asset_root,
            published_asset_root=publication.owned_root,
            assets_parent_fd=assets_parent_fd,
            state=state,
        )
    finally:
        if staging_fd >= 0:
            os.close(staging_fd)

    return asset


def approve_candidate(
    project_root: Path,
    docset_id: str,
    run_id: str,
    *,
    now: datetime,
    approved_by: str | None = None,
    min_score: int | None = None,
    allow_failing: bool = False,
    reapprove_legacy: bool = False,
    legacy_current_sha256: str | None = None,
    legacy_asset_sha256: str | None = None,
    known_gaps: list[str] | None = None,
    review: ReviewSummary | None = None,
    expected_base_asset_id: str | None = None,
    expected_base_asset_digest: str | None = None,
    enforce_expected_base: bool = False,
    expected_candidate_artifact_digests: dict[str, str] | None = None,
) -> Asset:
    """Approve one candidate while holding the complete per-docset lock."""
    transaction = store.begin_governance_transaction(project_root, docset_id)
    state = _ApprovalTransactionState()
    primary: BaseException | None = None
    try:
        return _approve_candidate_locked(
            transaction.project_root,
            docset_id,
            run_id,
            now=now,
            approved_by=approved_by,
            min_score=min_score,
            allow_failing=allow_failing,
            reapprove_legacy=reapprove_legacy,
            legacy_current_sha256=legacy_current_sha256,
            legacy_asset_sha256=legacy_asset_sha256,
            known_gaps=known_gaps,
            review=review,
            expected_base_asset_id=expected_base_asset_id,
            expected_base_asset_digest=expected_base_asset_digest,
            enforce_expected_base=enforce_expected_base,
            expected_candidate_artifact_digests=expected_candidate_artifact_digests,
            assets_parent_fd=transaction.assets_fd,
            docset_parent_fd=transaction.docset_fd,
            api_parent_fd=transaction.api_fd,
            _state=state,
        )
    except BaseException as exc:
        primary = exc
        raise
    finally:
        if state.recovery_required:
            transaction.abandon()
        else:
            try:
                transaction.close()
            except FoundryPublicationError as lock_error:
                rollback_error: BaseException | None = None
                if (
                    state.governance_snapshot is not None
                    and state.asset_root is not None
                ):
                    try:
                        _raise_approval_failure(
                            lock_error,
                            state.governance_snapshot,
                            state.staging_root,
                            state.asset_root,
                            published_asset_root=state.published_asset_root,
                            assets_parent_fd=transaction.assets_fd,
                            state=state,
                        )
                    except BaseException as exc:
                        rollback_error = exc
                if state.recovery_required:
                    transaction.abandon()
                    assert rollback_error is not None
                    raise rollback_error
                try:
                    transaction.force_close()
                except FoundryPublicationError as force_error:
                    if rollback_error is not None:
                        raise FoundryPublicationError(
                            f"{rollback_error}; lock recovery also failed: {force_error}"
                        ) from (primary or lock_error)
                    raise FoundryPublicationError(
                        f"{lock_error}; lock recovery also failed: {force_error}"
                    ) from (primary or lock_error)
                if rollback_error is not None:
                    raise rollback_error
                if primary is not None:
                    raise FoundryPublicationError(
                        f"approval failed: {primary}; {lock_error}"
                    ) from primary
                raise lock_error
