from __future__ import annotations

import pytest

from loop_apidoc.notebooklm.classify import classify_failure
from loop_apidoc.notebooklm.errors import (
    AuthRequired,
    NotebookInaccessible,
    SkillError,
    SkillSetupError,
    TransientError,
)
from loop_apidoc.notebooklm.runner import CommandResult


def _result(stdout: str = "", stderr: str = "", code: int = 1) -> CommandResult:
    return CommandResult(argv=["x"], returncode=code, stdout=stdout, stderr=stderr)


@pytest.mark.parametrize(
    "stdout, expected",
    [
        ("⚠️ Not authenticated. Run: ...", AuthRequired),
        ("❌ Timeout waiting for answer", TransientError),
        ("❌ Could not find query input", TransientError),
        ("❌ Failed to set up environment", SkillSetupError),
        ("❌ Error: navigation failed\nTraceback ...", NotebookInaccessible),
        ("some unexpected failure", SkillError),
    ],
)
def test_classify_failure_maps_markers(stdout, expected):
    error = classify_failure(_result(stdout=stdout))
    assert isinstance(error, expected)
    assert error.stdout == stdout


def test_classify_preserves_streams():
    error = classify_failure(_result(stdout="o", stderr="e"))
    assert error.stdout == "o"
    assert error.stderr == "e"


def test_auth_wins_over_error_marker_when_both_present():
    # Not-authenticated must take precedence over a generic ❌ Error: line.
    error = classify_failure(_result(stdout="⚠️ Not authenticated\n❌ Error: x"))
    assert isinstance(error, AuthRequired)
