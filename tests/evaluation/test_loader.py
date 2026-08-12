from __future__ import annotations

from pathlib import Path

import pytest

from loop_apidoc.evaluation.loader import load_replay_report
from loop_apidoc.evaluation.models import EvaluationInputError


def test_load_replay_report_rejects_missing_and_schema_invalid_files(
    tmp_path: Path,
) -> None:
    with pytest.raises(EvaluationInputError, match="baseline replay report does not exist"):
        load_replay_report(tmp_path / "missing.json", label="baseline")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    with pytest.raises(EvaluationInputError, match="candidate replay report schema mismatch"):
        load_replay_report(invalid, label="candidate")


def test_load_replay_report_rejects_unreadable_path(tmp_path: Path) -> None:
    unreadable = tmp_path / "report.json"
    unreadable.mkdir()

    with pytest.raises(EvaluationInputError, match="does not exist"):
        load_replay_report(unreadable, label="baseline")
