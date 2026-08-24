from __future__ import annotations

import hashlib
from pathlib import Path


_REQUIRED_ARTIFACTS = (
    "openapi.yaml",
    "provenance.json",
    "validation/report.json",
    "manifest.json",
)
_DECISION_ARTIFACT = "review/decision.json"


class CandidateBindingError(ValueError):
    """A candidate artifact set cannot safely support an approval binding."""


def artifact_digests(run_dir: Path) -> dict[str, str]:
    """Digest one complete reviewable candidate excluding its future decision."""

    for required in _REQUIRED_ARTIFACTS:
        path = run_dir / required
        if path.exists() and not path.is_file():
            raise CandidateBindingError(f"review artifact is not a file: {required}")
        if not path.is_file():
            raise CandidateBindingError(f"required review artifact missing: {required}")

    digests: dict[str, str] = {}
    for path in sorted(run_dir.rglob("*")):
        relative = path.relative_to(run_dir).as_posix()
        if relative == _DECISION_ARTIFACT:
            continue
        if path.is_symlink():
            raise CandidateBindingError(f"review artifact is unsafe: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise CandidateBindingError(f"review artifact is not a file: {relative}")
        try:
            digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise CandidateBindingError(
                f"review artifact is unreadable: {relative}"
            ) from exc
    return digests


def approval_artifact_digests(
    run_dir: Path,
    reviewed_digests: dict[str, str],
) -> dict[str, str]:
    """Add the post-review decision without making its binding self-referential."""

    decision_path = run_dir / _DECISION_ARTIFACT
    if decision_path.is_symlink() or not decision_path.is_file():
        raise CandidateBindingError("review decision artifact is missing or unsafe")
    try:
        decision_digest = hashlib.sha256(decision_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CandidateBindingError("review decision artifact is unreadable") from exc
    return {**reviewed_digests, _DECISION_ARTIFACT: decision_digest}
