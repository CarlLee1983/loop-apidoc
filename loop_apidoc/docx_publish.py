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


def write_prepared_docx(
    prepared: PreparedDocx,
    output: Path,
    *,
    stage_file: StageFile | None = None,
) -> DocxNormalizationResult:
    """Publish prepared bytes and provenance through an injectable filesystem seam."""
    sidecar = output.with_suffix(output.suffix + ".source.json")
    if output.exists() or sidecar.exists():
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
        output_temp.replace(output)
        output_published = True
        sidecar_temp.replace(sidecar)
    except OSError:
        if output_published:
            output.unlink(missing_ok=True)
        raise
    finally:
        if output_temp is not None:
            output_temp.unlink(missing_ok=True)
        if sidecar_temp is not None:
            sidecar_temp.unlink(missing_ok=True)
    return DocxNormalizationResult(output=output, provenance=sidecar)
