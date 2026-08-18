from __future__ import annotations

import ast
import re
from functools import cache
from pathlib import Path

from loop_apidoc.validate.models import IssueCode


REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "skills/loop-apidoc/reference/assemble-and-correction.md"
AGENTS = REPO_ROOT / "AGENTS.md"
# The operator's copy of the same list. Both manuals name all ten codes today,
# scattered through prose rather than gathered in a table, which is what makes
# them the fourth complete list nothing was keeping in sync (#144).
MANUALS = (
    REPO_ROOT / "docs/operator-manual.html",
    REPO_ROOT / "docs/operator-manual.en.html",
)

# Codes deliberately left out of an operator manual, keyed by manual, each with
# the reason. Empty because neither manual omits one; it exists so that leaving a
# code out stays a decision somebody wrote down, rather than a paragraph invented
# to make this test pass (the same reasoning as #135's exclusion list).
UNDOCUMENTED_IN_MANUAL: dict[str, dict[str, str]] = {}

# The reference document is the agent's routing table: per-code severity and how
# to read `target_file` / `field_path` / `requery_scope`. Adding an `IssueCode`
# member is a one-line change, and an unlisted code does not leave the agent with
# an incomplete document — it leaves the correction loop with no route, which is
# the fallback to guessing the core invariant exists to prevent. The reverse
# direction matters as much: a code left in prose after it was deleted has the
# agent responding to a signal that can no longer arrive (#136).
_TABLE_HEADING = "## Issue codes → what it means → how to respond"
_ISSUE_OBJECT_HEADING = "## The `Issue` object"
_CORRECTION_HEADING = "## Correction & fail-closed classification"

# A code span in SCREAMING_SNAKE_CASE, the underscore required: `ERROR` and
# `WARNING` are severities and plausible prose in a section about severity, and
# reporting them as unknown codes would make a correct document fail. Every code
# today carries an underscore, and a future single-word one surfaces as
# `undocumented` — loud, and on the side that is safe to be wrong about.
_CODE_SPAN = re.compile(r"`([A-Z]+(?:_[A-Z]+)+)`")
_TABLE_ROW = re.compile(r"^\|\s*`([A-Z]+(?:_[A-Z]+)+)`")


def _section(path: Path, heading: str) -> str:
    text = path.read_text(encoding="utf-8")

    assert heading in text, f"{path} no longer has the section {heading!r}"
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def _routing_table_codes() -> set[str]:
    """The first cell of every row in the routing table."""
    rows = [
        match.group(1)
        for line in _section(REFERENCE, _TABLE_HEADING).splitlines()
        for match in [_TABLE_ROW.match(line)]
        if match
    ]

    # Without this, a reformatted table (aligned pipes, say) parses as empty and
    # the test reports every code as undocumented — sending the next maintainer
    # to add rows that are already there.
    assert rows, f"no routing-table rows parsed from {REFERENCE}"
    return set(rows)


def _issue_object_codes() -> set[str]:
    """The alternation in the `Issue` object example — a second list in the same
    file, and the one an agent copies when it writes the shape out."""
    match = re.search(
        r'\{"code": "([A-Z_|]+)"', _section(REFERENCE, _ISSUE_OBJECT_HEADING)
    )

    assert match, "the Issue object example no longer states the code alternation"
    return set(match.group(1).split("|"))


@cache
def _module_constants() -> frozenset[str]:
    """Every module-level constant name this repository defines.

    The manuals have no table to parse, so codes are read from the prose's code
    spans — and prose also names real constants (`REQUIRED_BENCHMARK_CASES`,
    `SOURCE_ACQUISITION_EVIDENCE_TIERS`). Deriving the exclusion from the code
    keeps it true as those constants come and go, where a hand-written skip list
    would fail the next time the manual cites one. A name the repository does not
    define is reported, which is exactly the deleted-code direction. No issue
    code is also a constant, and the reverse-direction test proves it stays that
    way: shadow one and it disappears from the parse and reads as undocumented.
    """
    names: set[str] = set()
    for path in (*(REPO_ROOT / "loop_apidoc").rglob("*.py"), *(REPO_ROOT / "scripts").rglob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target] if isinstance(node, ast.AnnAssign) else []
            )
            names.update(t.id for t in targets if isinstance(t, ast.Name))
    return frozenset(names)


def _manual_codes(manual: Path) -> set[str]:
    """Codes named in a manual's prose: `<code>` spans that are not constants."""
    spans = set(re.findall(r"<code>([A-Z]+(?:_[A-Z]+)+)</code>", manual.read_text(encoding="utf-8")))
    return spans - _module_constants()


def _agents_correction_codes() -> set[str]:
    """Every code named in the response-by-intent bullets."""
    return set(_CODE_SPAN.findall(_section(AGENTS, _CORRECTION_HEADING)))


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


def test_both_operator_manuals_name_every_issue_code():
    """The manuals are where an operator reads what an issue means. A code that
    never reaches them leaves a list that still looks complete, one entry short."""
    for manual in MANUALS:
        excluded = UNDOCUMENTED_IN_MANUAL.get(manual.name, {})
        drift = _drift(_manual_codes(manual) | set(excluded))

        assert drift == {"undocumented": [], "documented_but_not_a_code": []}, (
            manual.name,
            drift,
        )


def test_every_manual_exclusion_names_a_live_code_and_a_reason():
    declared = {code.value for code in IssueCode}
    for name, excluded in UNDOCUMENTED_IN_MANUAL.items():
        assert name in {manual.name for manual in MANUALS}, name
        assert set(excluded) <= declared, sorted(set(excluded) - declared)
        assert all(reason.strip() for reason in excluded.values()), name
