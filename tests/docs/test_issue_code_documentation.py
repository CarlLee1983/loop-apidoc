from __future__ import annotations

import re
from pathlib import Path

from loop_apidoc.validate.models import IssueCode


REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "skills/loop-apidoc/reference/assemble-and-correction.md"
AGENTS = REPO_ROOT / "AGENTS.md"

# The reference document is the agent's routing table: per-code severity and how
# to read `target_file` / `field_path` / `requery_scope`. Adding an `IssueCode`
# member is a one-line change, and an unlisted code does not leave the agent with
# an incomplete document — it leaves the correction loop with no route, which is
# the fallback to guessing the core invariant exists to prevent. The reverse
# direction matters as much: a code left in prose after it was deleted has the
# agent responding to a signal that can no longer arrive (#136).
_TABLE_HEADING = "## Issue codes → what it means → how to respond"
_CORRECTION_HEADING = "## Correction & fail-closed classification"

# Codes are written the same way everywhere they appear: a code span in SCREAMING
# _SNAKE_CASE. Nothing else in these two sections is spelled that way, so a token
# this matches but the enum does not know is reported rather than filtered out.
_CODE_SPAN = re.compile(r"`([A-Z][A-Z_]{2,})`")


def _section(text: str, heading: str) -> str:
    body = text.split(heading, 1)[1]
    return body.split("\n## ", 1)[0]


def _routing_table_codes() -> set[str]:
    """The first cell of every row in the routing table."""
    section = _section(REFERENCE.read_text(encoding="utf-8"), _TABLE_HEADING)
    return {
        match.group(1)
        for line in section.splitlines()
        if line.startswith("| `")
        for match in [_CODE_SPAN.match(line[2:])]
        if match
    }


def _issue_object_codes() -> set[str]:
    """The alternation in the `Issue` object example — a second list in the same
    file, and the one an agent copies when it writes the shape out."""
    text = REFERENCE.read_text(encoding="utf-8")
    match = re.search(r'\{"code": "([A-Z_|]+)"', text)

    assert match, "the Issue object example no longer states the code alternation"
    return set(match.group(1).split("|"))


def _agents_correction_codes() -> set[str]:
    """Every code named in the response-by-intent bullets."""
    return set(_CODE_SPAN.findall(_section(AGENTS.read_text(encoding="utf-8"), _CORRECTION_HEADING)))


def _drift(documented: set[str]) -> dict[str, list[str]]:
    """Both directions, named: which side has the code the other lacks."""
    declared = {code.value for code in IssueCode}
    return {
        "undocumented": sorted(declared - documented),
        "documented_but_not_a_code": sorted(documented - declared),
    }


def test_the_routing_table_lists_every_issue_code():
    assert _drift(_routing_table_codes()) == {
        "undocumented": [],
        "documented_but_not_a_code": [],
    }


def test_the_issue_object_example_lists_every_issue_code():
    assert _drift(_issue_object_codes()) == {
        "undocumented": [],
        "documented_but_not_a_code": [],
    }


def test_every_issue_code_has_a_response_intent_in_agents_md():
    """A code with no bucket here is one an agent has no instruction for."""
    assert _drift(_agents_correction_codes()) == {
        "undocumented": [],
        "documented_but_not_a_code": [],
    }
