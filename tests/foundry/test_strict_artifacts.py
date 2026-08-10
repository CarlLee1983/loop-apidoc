from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.foundry.strict_artifacts import (
    StrictCoreExecutionError,
    require_eligible_strict_candidate,
)
from loop_apidoc.shadow.models import ShadowStage
from loop_apidoc.shadow.runner import ShadowExecutionFailure
from loop_apidoc.run.models import RunStatus


def _run_dir(
    tmp_path: Path,
    *,
    architecture_mode: str | None = "strict",
    execution: object | None = None,
) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    if architecture_mode is not None:
        (run_dir / "run.json").write_text(
            json.dumps({"architecture_mode": architecture_mode}), encoding="utf-8"
        )
    if execution is not None:
        core_dir = run_dir / "core"
        core_dir.mkdir()
        (core_dir / "execution.json").write_text(
            json.dumps(execution), encoding="utf-8"
        )
    return run_dir


def test_declared_strict_run_requires_execution_marker(tmp_path: Path) -> None:
    with pytest.raises(StrictCoreExecutionError, match="marker is missing"):
        require_eligible_strict_candidate(_run_dir(tmp_path))


def test_non_strict_run_rejects_strict_execution_artifact(tmp_path: Path) -> None:
    run_dir = _run_dir(
        tmp_path, architecture_mode="legacy", execution={"mode": "strict"}
    )

    with pytest.raises(StrictCoreExecutionError, match="non-strict run"):
        require_eligible_strict_candidate(run_dir)


def test_strict_execution_rejects_unreadable_or_non_object_payload(
    tmp_path: Path,
) -> None:
    unreadable = _run_dir(tmp_path / "unreadable")
    core_dir = unreadable / "core"
    core_dir.mkdir()
    (core_dir / "execution.json").write_text("{", encoding="utf-8")
    with pytest.raises(StrictCoreExecutionError, match="unreadable"):
        require_eligible_strict_candidate(unreadable)

    invalid = _run_dir(tmp_path / "invalid", execution=[])
    with pytest.raises(StrictCoreExecutionError, match="artifact is invalid"):
        require_eligible_strict_candidate(invalid)


def test_strict_execution_rejects_invalid_eligibility_fields(tmp_path: Path) -> None:
    base = {
        "mode": "strict",
        "blocking": True,
        "legacy_status": "passed",
        "candidate_eligible": True,
        "approval_requests": 0,
        "artifact_publications": 0,
        "core_verdict": "accept",
        "exact_supported_claims": 1,
    }
    run_dir = _run_dir(tmp_path / "mode", execution={**base, "mode": "shadow"})
    with pytest.raises(StrictCoreExecutionError, match="mode"):
        require_eligible_strict_candidate(run_dir)

    run_dir = _run_dir(
        tmp_path / "verdict", execution={**base, "core_verdict": "reject"}
    )
    with pytest.raises(StrictCoreExecutionError, match="core_verdict"):
        require_eligible_strict_candidate(run_dir)

    run_dir = _run_dir(
        tmp_path / "claims", execution={**base, "exact_supported_claims": True}
    )
    with pytest.raises(StrictCoreExecutionError, match="exact_supported_claims"):
        require_eligible_strict_candidate(run_dir)


def test_strict_adapter_records_a_shadow_execution_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from loop_apidoc.agentcli import strict

    def fail_shadow(**_kwargs: object) -> None:
        raise ShadowExecutionFailure(ShadowStage.BRIDGE, RuntimeError("boom"))

    monkeypatch.setattr(strict, "execute_shadow", fail_shadow)

    result = strict.run_strict_core_safely(
        manifest=None,  # type: ignore[arg-type]
        plan=None,  # type: ignore[arg-type]
        facts=None,  # type: ignore[arg-type]
        sources_root=tmp_path,
        legacy_report=None,  # type: ignore[arg-type]
        generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        run_dir=tmp_path / "run",
    )

    assert result.status == "error"
    assert result.error_path is not None
    payload = json.loads(Path(result.error_path).read_text(encoding="utf-8"))
    assert payload["stage"] == "bridge"


def test_strict_candidate_requires_a_valid_release_when_marker_is_eligible(
    tmp_path: Path,
) -> None:
    execution = {
        "mode": "strict",
        "blocking": True,
        "legacy_status": "passed",
        "candidate_eligible": True,
        "approval_requests": 0,
        "artifact_publications": 0,
        "core_verdict": "accept",
        "exact_supported_claims": 1,
    }
    run_dir = _run_dir(
        tmp_path, architecture_mode=None, execution=execution
    )

    with pytest.raises(StrictCoreExecutionError, match="missing a valid candidate release"):
        require_eligible_strict_candidate(run_dir)


def test_strict_candidate_rejects_invalid_run_descriptors(tmp_path: Path) -> None:
    unreadable = _run_dir(tmp_path / "unreadable")
    (unreadable / "run.json").write_text("{", encoding="utf-8")
    with pytest.raises(StrictCoreExecutionError, match="descriptor is unreadable"):
        require_eligible_strict_candidate(unreadable)

    invalid = _run_dir(tmp_path / "invalid")
    (invalid / "run.json").write_text("[]", encoding="utf-8")
    with pytest.raises(StrictCoreExecutionError, match="descriptor is invalid"):
        require_eligible_strict_candidate(invalid)

    unsupported = _run_dir(tmp_path / "unsupported", architecture_mode="future")
    with pytest.raises(StrictCoreExecutionError, match="invalid architecture mode"):
        require_eligible_strict_candidate(unsupported)


def test_strict_adapter_records_unexpected_errors_and_legacy_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from loop_apidoc.agentcli import strict

    def fail_shadow(**_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(strict, "execute_shadow", fail_shadow)
    error = strict.run_strict_core_safely(
        manifest=None,  # type: ignore[arg-type]
        plan=None,  # type: ignore[arg-type]
        facts=None,  # type: ignore[arg-type]
        sources_root=tmp_path,
        legacy_report=None,  # type: ignore[arg-type]
        generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        run_dir=tmp_path / "error-run",
    )
    assert error.status == "error"

    blocked = strict.write_strict_blocked_marker(
        run_dir=tmp_path / "blocked-run", legacy_status=RunStatus.FAILED
    )
    assert blocked.status == "blocked"
    execution = json.loads(
        (Path(blocked.core_dir) / "execution.json").read_text(encoding="utf-8")
    )
    assert execution["legacy_status"] == "failed"
