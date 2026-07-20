from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.run.models import RunStatus
from loop_apidoc.shadow.bridge import ShadowMetadataError
from loop_apidoc.shadow.models import (
    ShadowArtifacts,
    ShadowExecutionSummary,
    ShadowStage,
)
from loop_apidoc.shadow.runner import ShadowExecutionFailure, execute_shadow
from loop_apidoc.validate.models import ValidationReport


def write_shadow_artifacts(
    artifacts: ShadowArtifacts,
    core_dir: Path,
) -> ShadowExecutionSummary:
    core_dir.parent.mkdir(parents=True, exist_ok=True)
    payloads: tuple[tuple[str, Any], ...] = (
        ("source-set.json", artifacts.source_set),
        ("evidence.json", artifacts.evidence),
        ("runtime-result.json", artifacts.runtime_result),
        ("claims.json", artifacts.claims),
        ("contract.json", artifacts.contract),
        ("decision.json", artifacts.decision),
        ("workflow.json", artifacts.workflow),
        ("events.json", artifacts.events),
        ("comparison.json", artifacts.comparison),
    )
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{core_dir.name}-", dir=core_dir.parent)
    )
    try:
        for filename, payload in payloads:
            _write_json(staging_dir / filename, payload)
        staging_dir.replace(core_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    return ShadowExecutionSummary(
        status="ok",
        core_dir=str(core_dir),
        comparison_path=str(core_dir / "comparison.json"),
    )


def run_shadow_safely(
    *,
    manifest: Manifest,
    plan: NormalizationPlan,
    legacy_report: ValidationReport,
    legacy_status: RunStatus,
    generated_at: datetime,
    run_dir: Path,
) -> ShadowExecutionSummary:
    core_dir = run_dir / "core"
    try:
        artifacts = execute_shadow(
            manifest=manifest,
            plan=plan,
            legacy_report=legacy_report,
            legacy_status=legacy_status,
            generated_at=generated_at,
        )
    except ShadowExecutionFailure as failure:
        return _record_error(core_dir, failure.stage, failure.cause)
    except Exception as exc:
        return _record_error(core_dir, ShadowStage.SERVICE, exc)
    try:
        return write_shadow_artifacts(artifacts, core_dir)
    except Exception as exc:
        return _record_error(core_dir, ShadowStage.REPORT, exc)


def _record_error(
    core_dir: Path,
    stage: ShadowStage,
    exception: Exception,
) -> ShadowExecutionSummary:
    exception_type = type(exception).__name__
    message = _safe_message(stage, exception)
    error_path = core_dir / "error.json"
    try:
        core_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            error_path,
            {
                "status": "error",
                "stage": stage.value,
                "exception_type": exception_type,
                "message": message,
            },
        )
        saved_path: str | None = str(error_path)
    except Exception:
        saved_path = None
    return ShadowExecutionSummary(
        status="error",
        core_dir=str(core_dir),
        error_path=saved_path,
        stage=stage,
        exception_type=exception_type,
        message=message,
    )


def _safe_message(stage: ShadowStage, exception: Exception) -> str:
    if isinstance(exception, ShadowMetadataError):
        return str(exception).replace("\r", " ").replace("\n", " ")
    if stage is ShadowStage.REPORT:
        return "shadow artifacts could not be written"
    return f"shadow {stage.value} failed"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(
            _json_value(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _json_value(payload: Any) -> Any:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, tuple | list):
        return [_json_value(item) for item in payload]
    if isinstance(payload, dict):
        return {key: _json_value(value) for key, value in payload.items()}
    return payload
