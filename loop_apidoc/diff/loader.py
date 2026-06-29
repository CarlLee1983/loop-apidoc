from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.validate.models import ValidationReport


class DiffInputError(ValueError):
    """The run directory cannot be compared because an artifact is missing or invalid."""


@dataclass(frozen=True)
class RunArtifacts:
    run_dir: Path
    openapi: dict
    integration: dict | None
    provenance: ProvenanceDocument
    validation: ValidationReport
    manifest: Manifest


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise DiffInputError(f"required artifact missing: {label}")


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DiffInputError(f"cannot read {label}: {str(exc)[:200]}") from exc


def _load_json(path: Path, label: str) -> object:
    try:
        return json.loads(_read_text(path, label))
    except json.JSONDecodeError as exc:
        raise DiffInputError(f"{label} is not valid JSON: {exc}") from exc


def load_run_artifacts(run_dir: Path) -> RunArtifacts:
    if not run_dir.is_dir():
        raise DiffInputError(f"run directory does not exist: {run_dir}")

    openapi_path = run_dir / "openapi.yaml"
    provenance_path = run_dir / "provenance.json"
    validation_path = run_dir / "validation" / "report.json"
    manifest_path = run_dir / "manifest.json"
    integration_path = run_dir / "integration-contract.json"

    for path, label in (
        (openapi_path, "openapi.yaml"),
        (provenance_path, "provenance.json"),
        (validation_path, "validation/report.json"),
        (manifest_path, "manifest.json"),
    ):
        _require_file(path, label)

    try:
        openapi = yaml.safe_load(_read_text(openapi_path, "openapi.yaml"))
    except yaml.YAMLError as exc:
        raise DiffInputError(f"openapi.yaml is not valid YAML: {exc}") from exc
    if not isinstance(openapi, dict):
        raise DiffInputError("openapi.yaml must parse to an object")

    try:
        provenance = ProvenanceDocument.model_validate_json(
            _read_text(provenance_path, "provenance.json")
        )
        validation = ValidationReport.model_validate_json(
            _read_text(validation_path, "validation/report.json")
        )
        manifest = Manifest.model_validate_json(_read_text(manifest_path, "manifest.json"))
    except ValidationError as exc:
        raise DiffInputError(f"run artifact schema mismatch: {str(exc)[:200]}") from exc

    integration: dict | None = None
    if integration_path.exists():
        loaded = _load_json(integration_path, "integration-contract.json")
        if not isinstance(loaded, dict):
            raise DiffInputError("integration-contract.json must be an object")
        integration = loaded

    return RunArtifacts(
        run_dir=run_dir,
        openapi=openapi,
        integration=integration,
        provenance=provenance,
        validation=validation,
        manifest=manifest,
    )
