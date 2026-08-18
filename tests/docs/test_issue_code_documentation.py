from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from loop_apidoc.validate.models import IssueCode


REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "skills/loop-apidoc/reference/assemble-and-correction.md"
AGENTS = REPO_ROOT / "AGENTS.md"
# The operator's copy of the same list. Both manuals name all ten codes today,
# scattered through prose rather than gathered in a table, which is what makes
# them the fourth complete list nothing was keeping in sync (#144).
#
# `README.md` / `README.en.md` (nine of ten, no `SOURCE_FACTS_UNSCANNED`) and
# `docs/onboarding*.html` (eight) are deliberately out of scope: they describe a
# part of the pipeline and do not read as complete lists, so binding them would
# force prose written to satisfy a test rather than to tell an operator anything.
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


# The constants both manuals legitimately cite in the same SCREAMING_SNAKE shape
# as an issue code. Named one by one, with where each is defined, rather than
# derived by subtracting every module-level constant in the repository: that
# subtraction removes 248 names to neutralise these three, and any of the 248 can
# then mask a stale mention — a deleted code that survives as a constant (a
# legacy mapping, a migration table) would read as documented, which is the
# direction this check exists for.
CITED_CONSTANTS = {
    "REQUIRED_BENCHMARK_CASES": "scripts.quality_gate",
    "SANITIZED_BENCHMARK_CASES": "scripts.quality_gate",
    "SOURCE_ACQUISITION_EVIDENCE_TIERS": "scripts.quality_gate",
}

# A bare `<code>` span. The manuals write every code that way; a code moved into
# a highlighted example block (`<code class="language-bash">`) would read as
# undocumented, which is the right answer — an operator looking a code up needs
# it in the prose that explains it, not only in a command line.
_MANUAL_SPAN = re.compile(r"<code>([A-Z]+(?:_[A-Z]+)+)</code>")


def _manual_codes(manual: Path) -> set[str]:
    """Codes named in a manual's prose: `<code>` spans that are not cited constants."""
    return set(_MANUAL_SPAN.findall(manual.read_text(encoding="utf-8"))) - set(
        CITED_CONSTANTS
    )


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


@pytest.mark.parametrize("manual", MANUALS, ids=lambda path: path.name)
def test_the_operator_manual_names_every_issue_code(manual):
    """The manuals are where an operator reads what an issue means. A code that
    never reaches them leaves a list that still looks complete, one entry short.
    Parametrized so a drift in both translations is reported in one run — they
    are a pair and move together."""
    excluded = UNDOCUMENTED_IN_MANUAL.get(manual.name, {})

    assert _drift(_manual_codes(manual) | set(excluded)) == {
        "undocumented": [],
        "documented_but_not_a_code": [],
    }


def test_the_manuals_name_the_code_this_check_was_written_for():
    """`SOURCE_FACTS_UNSCANNED` is the code that separates the manuals from the
    partial lists: the READMEs stop one short of it. Naming it here means a
    rewrite that drops it fails for the original reason, not as one entry in a
    set difference."""
    for manual in MANUALS:
        assert "SOURCE_FACTS_UNSCANNED" in _manual_codes(manual), manual.name


def test_every_cited_constant_exists_and_is_not_an_issue_code():
    """The exclusion is only safe while these names are constants and nothing
    else. A renamed constant leaves a stale citation in the manual, and a code
    that ever takes one of these names would be excluded from the parse and read
    as undocumented — both are reported here, where the message is accurate."""
    for name, module in CITED_CONSTANTS.items():
        assert hasattr(importlib.import_module(module), name), (
            f"{module}.{name} is gone"
        )
    assert set(CITED_CONSTANTS).isdisjoint(code.value for code in IssueCode)


def test_a_cited_constant_is_excluded_but_a_code_is_not(tmp_path):
    """The parser, on a manual built for the purpose: a constant the prose cites
    is not read as a code, everything else in that shape is."""
    manual = tmp_path / "manual.html"
    manual.write_text(
        "<p><code>REQUIRED_BENCHMARK_CASES</code> <code>SOURCE_CONFLICT</code>"
        " <code>GHOST_CODE</code> <code>WARNING</code></p>",
        encoding="utf-8",
    )

    assert _manual_codes(manual) == {"SOURCE_CONFLICT", "GHOST_CODE"}


def test_every_manual_exclusion_names_a_live_code_and_a_reason():
    declared = {code.value for code in IssueCode}
    for name, excluded in UNDOCUMENTED_IN_MANUAL.items():
        assert name in {manual.name for manual in MANUALS}, name
        assert set(excluded) <= declared, sorted(set(excluded) - declared)
        assert all(reason.strip() for reason in excluded.values()), name
