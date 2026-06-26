from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class AgentConfig(BaseModel):
    """Locates the agent CLI and the local source directory it may read.

    The source documents stay on disk (no upload). Grounding is enforced by
    (a) restricting the agent to read-only file tools and (b) a system prompt
    that forbids prior knowledge and the web.
    """

    executable: str = "claude"
    sources_dir: Path
    model: str | None = None
    # Read-only: the agent may read files but must not edit, run shell, or reach
    # the network — so the only information it can use is the local sources.
    allowed_tools: tuple[str, ...] = ("Read", "Grep", "Glob")
    timeout_seconds: float = 300.0
