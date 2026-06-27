from __future__ import annotations


class ExtractionError(Exception):
    """Base class for agent-CLI extraction failures (spec §11)."""

    def __init__(self, message: str, *, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.stdout = stdout
        self.stderr = stderr


class TransientError(ExtractionError):
    """A timeout or transient/quota failure eligible for limited technical
    retries, counted separately from the three correction rounds (spec §11)."""


class MalformedOutput(ExtractionError):
    """The agent CLI exited 0 but output could not be parsed; raw stdout/stderr
    are preserved and the run stops (spec §11)."""


class SkillError(ExtractionError):
    """Unclassified non-zero agent-CLI failure; raw output preserved."""
