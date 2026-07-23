from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from loop_apidoc.diff.models import DiffFinding, DiffReport
from loop_apidoc.review.models import (
    ReviewBinding,
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
)


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


def diff_subject(finding: DiffFinding) -> ReviewSubject:
    digest = canonical_digest(finding.model_dump(mode="json"))
    return ReviewSubject(
        id=f"diff:{digest}",
        kind=ReviewSubjectKind.DIFF,
        location=finding.location,
        summary=finding.summary,
    )


def validation_subject(issue: Issue) -> ReviewSubject:
    digest = canonical_digest(issue.model_dump(mode="json"))
    return ReviewSubject(
        id=f"validation:{digest}",
        kind=ReviewSubjectKind.VALIDATION,
        location=issue.location,
        summary=f"{issue.code.value}: {issue.suggested_fix}",
    )
