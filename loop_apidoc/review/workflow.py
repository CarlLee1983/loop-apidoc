from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.diff import DiffInputError, build_diff_report, load_run_artifacts
from loop_apidoc.foundry import approve, importer, paths, store
from loop_apidoc.foundry.models import FoundryInputError, ReviewState, ReviewSummary
from loop_apidoc.review.binding import (
    artifact_digests,
    build_binding,
    diff_subject,
    evidence_for_diff_location,
    load_exact_evidence_by_target,
    validation_subject,
)
from loop_apidoc.review.models import (
    ApprovalResult,
    ReviewConflictError,
    ReviewDecision,
    ReviewDisposition,
    ReviewDraft,
    ReviewInputError,
    ReviewKey,
    ReviewMode,
    ReviewRequest,
    ReviewSnapshot,
    ReviewStateError,
    ReviewSubjectKind,
)
from loop_apidoc.score.models import ScoreReport, ScoreStatus


def _load_score(run_dir: Path) -> ScoreReport | None:
    path = run_dir / "score" / "score.json"
    if not path.exists():
        return None
    if not path.is_file():
        raise ReviewInputError("review score artifact is not a file: score/score.json")
    try:
        return ScoreReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReviewInputError(f"review score artifact is invalid: {exc}") from exc


class ReviewWorkflow:
    """Deep seam for a single-user Foundry candidate-review lifecycle."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def open_review(self, request: ReviewRequest) -> ReviewSnapshot:
        candidate_dir = self._import_or_reopen(request)
        return self._snapshot(request.docset_id, candidate_dir.name)

    def save_decision(self, key: ReviewKey, draft: ReviewDraft) -> ReviewSnapshot:
        snapshot = self._snapshot(key.docset_id, key.candidate_run_id)
        self._validate_draft(snapshot, draft)
        decision = ReviewDecision(
            binding=snapshot.binding,
            items=draft.items,
            handoff=draft.handoff,
            waivers=draft.waivers,
            note=draft.note,
            saved_at=datetime.now(timezone.utc),
        )
        store.save_review_decision(
            self.project_root, key.docset_id, key.candidate_run_id, decision
        )
        return snapshot.model_copy(update={"decision": decision})

    def approve_review(
        self, key: ReviewKey, draft: ReviewDraft, *, now: datetime
    ) -> ApprovalResult:
        saved = self.save_decision(key, draft)
        fresh = self._snapshot(key.docset_id, key.candidate_run_id)
        if fresh.binding != saved.binding:
            raise ReviewConflictError("candidate/base evidence changed after decision save")

        needs_follow_up, known_gaps, open_count = self._review_outcome(fresh, draft)
        summary = ReviewSummary(
            state=(ReviewState.NEEDS_FOLLOW_UP if needs_follow_up else ReviewState.REVIEWED),
            decision_path="artifacts/review/decision.json",
            open_handoff_count=open_count,
        )
        try:
            asset = approve.approve_candidate(
                self.project_root,
                key.docset_id,
                key.candidate_run_id,
                now=now,
                approved_by=None,
                allow_failing=True,
                known_gaps=known_gaps,
                review=summary,
            )
        except FoundryInputError as exc:
            raise ReviewInputError(str(exc)) from exc
        return ApprovalResult(
            asset_id=asset.asset_id,
            current_asset=asset.asset_id,
            needs_follow_up=needs_follow_up,
            open_handoff_count=open_count,
        )

    def _import_or_reopen(self, request: ReviewRequest) -> Path:
        try:
            store.load_docset(self.project_root, request.docset_id)
            input_artifacts = load_run_artifacts(request.run_dir)
            input_digests = artifact_digests(request.run_dir)
        except (FoundryInputError, DiffInputError, ReviewInputError) as exc:
            raise ReviewInputError(str(exc)) from exc

        candidate_dir = paths.candidate_dir(
            self.project_root, request.docset_id, input_artifacts.run_dir.name
        )
        if candidate_dir.exists():
            try:
                load_run_artifacts(candidate_dir)
                candidate_digests = artifact_digests(candidate_dir)
            except (DiffInputError, ReviewInputError) as exc:
                raise ReviewInputError(f"existing candidate is invalid: {exc}") from exc
            if candidate_digests != input_digests:
                raise ReviewInputError(
                    f"candidate collision has different artifacts: {input_artifacts.run_dir.name}"
                )
            return candidate_dir
        try:
            return importer.import_run(
                self.project_root, request.docset_id, request.run_dir
            ).candidate_dir
        except FoundryInputError as exc:
            raise ReviewInputError(str(exc)) from exc

    def _snapshot(self, docset_id: str, candidate_run_id: str) -> ReviewSnapshot:
        candidate_dir = paths.candidate_dir(
            self.project_root, docset_id, candidate_run_id
        )
        if not candidate_dir.is_dir():
            raise ReviewInputError(f"candidate not found: {candidate_run_id}")
        try:
            candidate = load_run_artifacts(candidate_dir)
            score = _load_score(candidate_dir)
            current = store.load_current(self.project_root, docset_id)
            if current is None:
                mode = ReviewMode.BASELINE
                base_asset_id = None
                base_dir = None
                diff = None
            else:
                asset = store.load_asset(
                    self.project_root, docset_id, current.current_asset
                )
                base_asset_id = asset.asset_id
                base_dir = paths.asset_artifacts_dir(
                    self.project_root, docset_id, asset.asset_id
                )
                base = load_run_artifacts(base_dir)
                diff = build_diff_report(base, candidate)
                mode = ReviewMode.UPDATE
            binding = build_binding(
                docset_id=docset_id,
                candidate_run_id=candidate_run_id,
                candidate_dir=candidate_dir,
                base_asset_id=base_asset_id,
                base_dir=base_dir,
                diff=diff,
            )
            decision = store.load_review_decision(
                self.project_root, docset_id, candidate_run_id
            )
        except (DiffInputError, FoundryInputError, ReviewInputError) as exc:
            raise ReviewInputError(str(exc)) from exc
        if decision is not None and decision.binding != binding:
            raise ReviewConflictError("saved review decision is stale for current evidence")
        exact_evidence = load_exact_evidence_by_target(candidate_dir)
        subjects = [
            validation_subject(issue, exact_evidence.get(issue.location))
            for issue in candidate.validation.issues
        ]
        if diff is not None:
            subjects = [
                diff_subject(
                    finding,
                    evidence_for_diff_location(finding.location, exact_evidence),
                )
                for finding in diff.findings
            ] + subjects
        return ReviewSnapshot(
            key=ReviewKey(docset_id=docset_id, candidate_run_id=candidate_run_id),
            binding=binding,
            mode=mode,
            validation=candidate.validation,
            provenance=candidate.provenance,
            score=score,
            diff=diff,
            subjects=subjects,
            decision=decision,
        )

    def _validate_draft(self, snapshot: ReviewSnapshot, draft: ReviewDraft) -> None:
        if draft.binding != snapshot.binding:
            raise ReviewConflictError("review draft is stale for current evidence")
        known = {subject.id: subject.kind for subject in snapshot.subjects}
        seen: set[str] = set()
        for item in draft.items:
            if item.subject_id in seen:
                raise ReviewStateError(f"duplicate review subject: {item.subject_id}")
            seen.add(item.subject_id)
            if item.subject_kind is ReviewSubjectKind.MANUAL:
                continue
            if known.get(item.subject_id) is not item.subject_kind:
                raise ReviewStateError(f"unknown review subject: {item.subject_id}")
        allowed_handoff_ids = seen | set(known)
        for handoff in draft.handoff:
            unknown = set(handoff.subject_ids) - allowed_handoff_ids
            if unknown:
                raise ReviewStateError(
                    f"handoff references unknown review subjects: {', '.join(sorted(unknown))}"
                )
        for waiver in draft.waivers:
            subject = next((item for item in snapshot.subjects if item.id == waiver.subject_id), None)
            if subject is None:
                raise ReviewStateError(f"waiver references unknown review subject: {waiver.subject_id}")
            matching = [evidence for evidence in subject.evidence if evidence.claim_identity == waiver.claim_identity]
            if not matching:
                raise ReviewStateError("waiver claim must be supported by the review subject evidence")
            if any(item.relationship in {"insufficient", "contradicts"} for item in matching):
                raise ReviewStateError("waiver cannot apply to insufficient or contradictory evidence")

    def _review_outcome(
        self, snapshot: ReviewSnapshot, draft: ReviewDraft
    ) -> tuple[bool, list[str], int]:
        items = {item.subject_id: item for item in draft.items}
        unresolved: list[str] = []
        for subject in snapshot.subjects:
            item = items.get(subject.id)
            if item is None or item.disposition is not ReviewDisposition.ACCEPT:
                unresolved.append(f"{subject.location}: {subject.summary}")
        for item in draft.items:
            if item.subject_kind is ReviewSubjectKind.MANUAL and (
                item.disposition is not ReviewDisposition.ACCEPT
            ):
                unresolved.append(item.note or f"manual review item: {item.subject_id}")
        open_handoffs = [task for task in draft.handoff if task.status == "open"]
        unresolved.extend(task.instruction for task in open_handoffs)
        if not snapshot.validation.ok:
            unresolved.extend(
                f"validation {issue.code.value} at {issue.location}"
                for issue in snapshot.validation.errors()
            )
        if snapshot.score is not None and snapshot.score.status is not ScoreStatus.PASS:
            unresolved.append(
                f"score {snapshot.score.score} is {snapshot.score.status.value} "
                f"(minimum {snapshot.score.min_score})"
            )
        known_gaps = list(dict.fromkeys(unresolved))
        return bool(known_gaps), known_gaps, len(open_handoffs)
