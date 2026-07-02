from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from loop_apidoc.diff.loader import DiffInputError, load_run_artifacts
from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.models import FoundryInputError


@dataclass(frozen=True)
class ImportResult:
    run_id: str
    candidate_dir: Path


def import_run(
    project_root: Path,
    docset_id: str,
    run_dir: Path,
    *,
    overwrite: bool = False,
) -> ImportResult:
    # Fail fast if the docset is unknown.
    store.load_docset(project_root, docset_id)

    # Reuse the diff loader as the completeness gate for a run dir.
    try:
        load_run_artifacts(run_dir)
    except DiffInputError as exc:
        raise FoundryInputError(f"run directory is not a valid run: {exc}") from exc

    run_id = run_dir.name
    dest = paths.candidate_dir(project_root, docset_id, run_id)
    if dest.exists():
        if not overwrite:
            raise FoundryInputError(f"candidate already exists: {run_id}")
        shutil.rmtree(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(run_dir, dest)
    return ImportResult(run_id=run_id, candidate_dir=dest)
