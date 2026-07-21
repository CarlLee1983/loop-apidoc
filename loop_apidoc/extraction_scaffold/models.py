"""Immutable values emitted by the extraction-scaffold projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScaffoldEndpoint:
    """One extraction-shaped endpoint document and its output filename."""

    filename: str
    body: dict[str, Any]


@dataclass(frozen=True)
class ScaffoldBundle:
    """All non-authoritative artifacts before they are written."""

    inventory: dict[str, Any]
    endpoints: tuple[ScaffoldEndpoint, ...]
    report: dict[str, Any]

    def summary(self, output: str) -> dict[str, Any]:
        """Return the command's concise success payload."""
        return {
            "endpoints": self.report["endpoints"],
            "fields": self.report["fields"],
            "examples": self.report["examples_projected"],
            "omitted_tables": self.report["omitted_tables"],
            "output": output,
        }
