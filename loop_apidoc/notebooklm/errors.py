from __future__ import annotations


class NotebookLMError(Exception):
    """Base class for NotebookLM adapter failures (spec §11)."""

    def __init__(self, message: str, *, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.stdout = stdout
        self.stderr = stderr


class AuthRequired(NotebookLMError):
    """Browser session is not authenticated; stop and provide login
    instructions (spec §11: NotebookLM 未驗證 -> 停止並提供登入指示)."""


class NotebookInaccessible(NotebookLMError):
    """The notebook could not be opened; stop, do not normalize (spec §11)."""


class TransientError(NotebookLMError):
    """A timeout or transient/quota failure eligible for limited technical
    retries, counted separately from the three correction rounds (spec §11)."""


class MalformedOutput(NotebookLMError):
    """Skill exited 0 but output could not be parsed; raw stdout/stderr are
    preserved and the run stops (spec §11)."""


class SkillSetupError(NotebookLMError):
    """The run.py wrapper failed to bootstrap the skill environment."""


class SkillError(NotebookLMError):
    """Unclassified non-zero skill failure; raw output preserved."""
