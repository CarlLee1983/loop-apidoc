"""Staged publication of prepared DOCX normalization artifacts with write rollback."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from loop_apidoc.docx_models import (
    DocxNormalizationError,
    DocxNormalizationResult,
    PreparedDocx,
    StageFile,
)


def _stage_file(target: Path, content: bytes) -> Path:
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        staged = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return staged


def _publish_no_clobber(staged: Path, target: Path) -> None:
    try:
        os.link(staged, target)
    except FileExistsError as exc:
        raise DocxNormalizationError(
            "DOCX normalization output already exists"
        ) from exc


def _rollback_if_owned(staged: Path, target: Path) -> None:
    try:
        staged_metadata = staged.stat()
        target_metadata = target.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (staged_metadata.st_dev, staged_metadata.st_ino) == (
        target_metadata.st_dev,
        target_metadata.st_ino,
    ):
        target.unlink()


def write_prepared_docx(
    prepared: PreparedDocx,
    output: Path,
    *,
    stage_file: StageFile | None = None,
) -> DocxNormalizationResult:
    """Publish prepared bytes and provenance through an injectable filesystem seam."""
    sidecar = output.with_suffix(output.suffix + ".source.json")
    if (
        output.exists()
        or output.is_symlink()
        or sidecar.exists()
        or sidecar.is_symlink()
    ):
        raise DocxNormalizationError("DOCX normalization output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    provenance_bytes = json.dumps(
        prepared.provenance, ensure_ascii=False, indent=2
    ).encode("utf-8")
    output_temp: Path | None = None
    sidecar_temp: Path | None = None
    output_published = False
    stage = stage_file or _stage_file
    try:
        output_temp = stage(output, prepared.markdown)
        sidecar_temp = stage(sidecar, provenance_bytes)
        _publish_no_clobber(output_temp, output)
        output_published = True
        _publish_no_clobber(sidecar_temp, sidecar)
    except (DocxNormalizationError, OSError):
        if output_published and output_temp is not None:
            _rollback_if_owned(output_temp, output)
        raise
    finally:
        if output_temp is not None:
            output_temp.unlink(missing_ok=True)
        if sidecar_temp is not None:
            sidecar_temp.unlink(missing_ok=True)
    return DocxNormalizationResult(output=output, provenance=sidecar)
