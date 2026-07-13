from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.source_quality.models import QualityObservation


class SourceQualityInputError(ValueError):
    pass


def load_manifest(path: Path) -> Manifest:
    try:
        return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise SourceQualityInputError(f"invalid manifest: {path}: {exc}") from exc


def load_observations(path: Path) -> list[QualityObservation]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("observations must be a JSON array")
        return [QualityObservation.model_validate(item) for item in payload]
    except (OSError, ValueError, ValidationError) as exc:
        raise SourceQualityInputError(f"invalid observations: {path}: {exc}") from exc
