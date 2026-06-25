from __future__ import annotations

import pytest

from loop_apidoc.notebooklm.errors import (
    AuthRequired,
    MalformedOutput,
    NotebookInaccessible,
    NotebookLMError,
    SkillError,
    SkillSetupError,
    TransientError,
)


def test_base_error_carries_streams():
    error = NotebookLMError("boom", stdout="out", stderr="err")
    assert error.message == "boom"
    assert error.stdout == "out"
    assert error.stderr == "err"
    assert str(error) == "boom"


@pytest.mark.parametrize(
    "cls",
    [AuthRequired, NotebookInaccessible, TransientError, MalformedOutput, SkillSetupError, SkillError],
)
def test_subclasses_are_notebooklm_errors(cls):
    error = cls("x")
    assert isinstance(error, NotebookLMError)
    assert error.stdout == ""
    assert error.stderr == ""
