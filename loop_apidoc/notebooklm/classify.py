from __future__ import annotations

from loop_apidoc.notebooklm.errors import (
    AuthRequired,
    NotebookInaccessible,
    NotebookLMError,
    SkillError,
    SkillSetupError,
    TransientError,
)
from loop_apidoc.notebooklm.runner import CommandResult

# Markers grounded in notebooklm-skill source (see Plan 2 reference contract).
_NOT_AUTH = "Not authenticated"
_TIMEOUT = "Timeout waiting for answer"
_NO_INPUT = "Could not find query input"
_SETUP_FAILED = "Failed to set up environment"
_NAV_ERROR = "❌ Error:"


def classify_failure(result: CommandResult) -> NotebookLMError:
    """Map a non-zero skill result to a typed error. First match wins."""
    text = f"{result.stdout}\n{result.stderr}"
    streams = {"stdout": result.stdout, "stderr": result.stderr}
    if _NOT_AUTH in text:
        return AuthRequired("NotebookLM browser session is not authenticated", **streams)
    if _TIMEOUT in text:
        return TransientError("Timed out waiting for a NotebookLM answer", **streams)
    if _NO_INPUT in text:
        return TransientError("NotebookLM query input was not found", **streams)
    if _SETUP_FAILED in text:
        return SkillSetupError("notebooklm-skill environment setup failed", **streams)
    if _NAV_ERROR in text:
        return NotebookInaccessible("Could not open the NotebookLM notebook", **streams)
    return SkillError(f"notebooklm-skill exited with code {result.returncode}", **streams)
