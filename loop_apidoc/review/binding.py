from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from loop_apidoc.diff.models import DiffFinding, DiffReport
from loop_apidoc.review.models import (
    ReviewBinding,
    ReviewEvidence,
    ReviewInputError,
    ReviewSubject,
    ReviewSubjectKind,
)
from loop_apidoc.validate.models import Issue

_ARTIFACTS = (
    "openapi.yaml",
    "provenance.json",
    "validation/report.json",
    "manifest.json",
    "integration-contract.json",
    "preparation-report.json",
    "core/evidence.json",
    "core/projections/review-data.json",
)

_REVIEW_EVIDENCE = TypeAdapter(tuple[ReviewEvidence, ...])
_HTTP_METHODS = frozenset({
    "GET", "PUT", "POST", "DELETE", "PATCH", "OPTIONS", "HEAD", "TRACE",
})


def canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def artifact_digests(run_dir: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for relative in _ARTIFACTS:
        path = run_dir / relative
        if path.exists():
            if not path.is_file():
                raise ReviewInputError(f"review artifact is not a file: {relative}")
            digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    for required in _ARTIFACTS[:4]:
        if required not in digests:
            raise ReviewInputError(f"required review artifact missing: {required}")
    return digests


def build_binding(
    *,
    docset_id: str,
    candidate_run_id: str,
    candidate_dir: Path,
    base_asset_id: str | None,
    base_dir: Path | None,
    diff: DiffReport | None,
) -> ReviewBinding:
    base_digests = artifact_digests(base_dir) if base_dir is not None else {}
    return ReviewBinding(
        docset_id=docset_id,
        candidate_run_id=candidate_run_id,
        candidate_artifact_digests=artifact_digests(candidate_dir),
        base_asset_id=base_asset_id,
        base_artifact_digests=base_digests,
        diff_digest=canonical_digest(diff.model_dump(mode="json")) if diff else None,
    )


def load_exact_evidence_by_target(run_dir: Path) -> dict[str, list[ReviewEvidence]]:
    """Load verified Core evidence when both optional review artifacts exist.

    A shadow run that did not produce Core artifacts remains reviewable. When either
    artifact is present, though, malformed or internally inconsistent evidence is a
    review input error rather than an excuse to hide it.
    """
    evidence_path = run_dir / "core" / "evidence.json"
    review_data_path = run_dir / "core" / "projections" / "review-data.json"
    if not evidence_path.exists() and not review_data_path.exists():
        return {}
    if not evidence_path.is_file() or not review_data_path.is_file():
        raise ReviewInputError("Core review evidence artifacts are incomplete")
    try:
        evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        review_payload = json.loads(review_data_path.read_text(encoding="utf-8"))
        fragments = {
            item["id"]: item
            for item in evidence_payload["fragments"]
        }
        relationships = review_payload["relationships"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ReviewInputError(f"Core review evidence artifacts are invalid: {exc}") from exc

    entries: dict[str, list[dict[str, Any]]] = {}
    for relationship in relationships:
        if relationship.get("relationship") not in {
            "explicit_support", "derived_support", "contradicts", "insufficient"
        }:
            continue
        fragment = fragments.get(relationship.get("fragment_id"))
        if fragment is None:
            raise ReviewInputError("Core review evidence references a missing fragment")
        entries.setdefault(relationship["target"], []).append({
            "claim_identity": relationship["claim_identity"],
            "claim_path": relationship["claim_path"],
            "relationship": relationship["relationship"],
            "source_id": relationship["source_id"],
            "source_locator": relationship["source_locator"],
            "fragment_locator": fragment["locator"],
            "fragment_digest": fragment["fragment_digest"],
            "normalized_excerpt": fragment.get("normalized_excerpt"),
        })
    try:
        return {
            target: list(_REVIEW_EVIDENCE.validate_python(items))
            for target, items in entries.items()
        }
    except ValidationError as exc:
        raise ReviewInputError(f"Core review evidence artifacts are invalid: {exc}") from exc


def evidence_for_diff_location(
    location: str, evidence_by_target: dict[str, list[ReviewEvidence]]
) -> list[ReviewEvidence]:
    """Resolve only unambiguous diff operation locations to Core targets."""
    method, separator, remainder = location.partition(" ")
    if method in _HTTP_METHODS and separator and remainder.startswith("/"):
        path, suffix_separator, suffix = remainder.partition(" ")
        target = f"paths.{path}.{method.lower()}"
        if suffix_separator:
            # A field-level diff must match an exact normalized claim target.  Falling
            # back to operation evidence would falsely imply support for that field.
            return evidence_by_target.get(f"{target}.{suffix}", [])
        return evidence_by_target.get(target, [])
    return evidence_by_target.get(location, [])


def diff_subject(
    finding: DiffFinding, evidence: list[ReviewEvidence] | None = None
) -> ReviewSubject:
    digest = canonical_digest(finding.model_dump(mode="json"))
    return ReviewSubject(
        id=f"diff:{digest}",
        kind=ReviewSubjectKind.DIFF,
        location=finding.location,
        summary=finding.summary,
        evidence=evidence or [],
    )


def validation_subject(
    issue: Issue, evidence: list[ReviewEvidence] | None = None
) -> ReviewSubject:
    digest = canonical_digest(issue.model_dump(mode="json"))
    return ReviewSubject(
        id=f"validation:{digest}",
        kind=ReviewSubjectKind.VALIDATION,
        location=issue.location,
        summary=f"{issue.code.value}: {issue.suggested_fix}",
        evidence=evidence or [],
    )
