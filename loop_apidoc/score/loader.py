from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.score.models import ScoreInputError, ScoreInputs
from loop_apidoc.validate.models import ValidationReport

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ScoreInputError(f"required artifact missing: {label}")


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScoreInputError(f"cannot read {label}: {str(exc)[:200]}") from exc


def _validate_model(model: type[_ModelT], path: Path, label: str) -> _ModelT:
    try:
        return model.model_validate_json(_read_text(path, label))
    except ValidationError as exc:
        raise ScoreInputError(f"{label} schema mismatch: {str(exc)[:200]}") from exc


def _load_json_object(path: Path, label: str) -> dict:
    try:
        loaded = json.loads(_read_text(path, label))
    except json.JSONDecodeError as exc:
        raise ScoreInputError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ScoreInputError(f"{label} must be a JSON object")
    return loaded


def load_score_inputs(run_dir: Path) -> ScoreInputs:
    if not run_dir.is_dir():
        raise ScoreInputError(f"run directory does not exist: {run_dir}")

    openapi_path = run_dir / "openapi.yaml"
    provenance_path = run_dir / "provenance.json"
    validation_path = run_dir / "validation" / "report.json"
    manifest_path = run_dir / "manifest.json"
    plan_path = run_dir / "plan" / "normalization-plan.json"

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
        raise ScoreInputError(f"openapi.yaml is not valid YAML: {exc}") from exc
    if not isinstance(openapi, dict):
        raise ScoreInputError("openapi.yaml must parse to an object")

    plan = None
    if plan_path.exists():
        plan = _load_json_object(plan_path, "plan/normalization-plan.json")

    return ScoreInputs(
        run_dir=run_dir,
        openapi=openapi,
        validation=_validate_model(
            ValidationReport,
            validation_path,
            "validation/report.json",
        ),
        provenance=_validate_model(ProvenanceDocument, provenance_path, "provenance.json"),
        manifest=_validate_model(Manifest, manifest_path, "manifest.json"),
        plan=plan,
        review_html_exists=(run_dir / "review.html").is_file(),
        validation_markdown_exists=(run_dir / "validation" / "report.md").is_file(),
    )
