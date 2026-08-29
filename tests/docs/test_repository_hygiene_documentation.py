from __future__ import annotations

import re
from pathlib import Path

from scripts import quality_gate


# The section is the human-readable presentation of the same inventory; the
# tuple in `scripts/quality_gate.py` is the machine-readable truth. This test
# keeps the table from drifting away from it — it never generates the table.
AGENTS = Path(__file__).resolve().parents[2] / "AGENTS.md"
HEADING = "## Repository hygiene"

_CODE_SPAN = re.compile(r"`([^`\n]+)`")


def _section() -> str:
    text = AGENTS.read_text(encoding="utf-8")
    start = text.find(HEADING)
    assert start != -1, f"{HEADING} not found in {AGENTS}"
    end = text.find("\n## ", start + len(HEADING))
    return text[start:] if end == -1 else text[start:end]


_SEPARATOR_ROW = re.compile(r"^[|\s:-]+$")


def _table_rows() -> list[str]:
    """The inventory table's data rows — pipe lines inside the section, minus
    the header and the `| --- |` separator. The surrounding prose is
    deliberately out of scope: it names `.work/`, `benchmarks/<case>/work/`,
    `benchmarks/<case>/sources/`, and the deliberately-excluded tool caches
    (`node_modules/`, `.venv/`, `dist/`, `graft/`, `htmlcov/`, `__pycache__/`,
    `benchmark_out/`, `benchmark_work/`, `output/`) precisely to say they are
    *not* forbidden, and no parser should read those as entries. If that excluded
    set is ever promoted into a table of its own, this selector must learn to
    tell the two tables apart."""
    rows = [line for line in _section().splitlines() if line.lstrip().startswith("|")]
    body = [row for row in rows if not _SEPARATOR_ROW.match(row)]
    assert len(body) >= 2, "inventory table has no header and no data rows"
    return body[1:]


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _documented_roots() -> dict[str, str]:
    """Every root the table names, mapped to its declared kind. Only the first
    cell may name a root, so a description mentioning `benchmarks/` or
    `examples/` cannot register a phantom entry, and each row must contribute
    exactly one root, so a row written `runs` instead of `runs/` fails loudly
    instead of vanishing — the same guard `test_acquisition_evidence_tiers.py`
    puts on its row count."""
    documented: dict[str, str] = {}
    rows = _table_rows()
    for row in rows:
        cells = _cells(row)
        assert len(cells) == 3, f"row must be root | kind | reason: {row!r}"
        named = [
            span[:-1]
            for span in _CODE_SPAN.findall(cells[0])
            if span.endswith("/") and span.count("/") == 1
        ]
        assert len(named) == 1, f"row must name exactly one root: {row!r}"
        documented[named[0]] = cells[1]
    assert len(documented) == len(rows), "the table repeats a root"
    return documented


RUN_ARTIFACT = "run artifact"
THIRD_PARTY = "third-party material"


def test_documented_hygiene_table_matches_the_controlled_list():
    assert set(_documented_roots()) == set(quality_gate.REPOSITORY_HYGIENE_FORBIDDEN_ROOTS)


def test_documented_kinds_match_the_disclosure_subset():
    """The clutter/disclosure split is the load-bearing distinction — it decides
    whether the gate tells an operator to escalate to the repository owner — so
    it gets the same doc-vs-code guard as the inventory itself."""
    documented = _documented_roots()
    third_party = {root for root, kind in documented.items() if kind == THIRD_PARTY}

    assert set(documented.values()) <= {RUN_ARTIFACT, THIRD_PARTY}
    assert third_party == set(quality_gate.REPOSITORY_HYGIENE_DISCLOSURE_ROOTS)


def test_the_section_points_at_the_enforced_inventory():
    """A reader who follows the section must land on something runnable: the
    file, the constant, and the test that checks the pair."""
    section = _section()

    assert "scripts/quality_gate.py" in section
    assert "REPOSITORY_HYGIENE_FORBIDDEN_ROOTS" in section
    assert "REPOSITORY_HYGIENE_DISCLOSURE_ROOTS" in section
    assert "test_documented_hygiene_table_matches_the_controlled_list" in section
    assert len(quality_gate.REPOSITORY_HYGIENE_FORBIDDEN_ROOTS) > 0, "inventory is empty"


def test_the_section_states_the_narrowing_criterion():
    """The criterion is what stops the rule growing into a `work` substring
    match; prose that only lists the roots would lose it. Whitespace is
    collapsed first so a re-wrapped paragraph is not a failure."""
    section = " ".join(_section().split())

    # A unique phrase, not the bare word "first": the point of the assertion is
    # that the narrowing clause survives, and "first" alone survives anything.
    assert "**first** path segment" in section
    # The `"/" in path` guard: a root-level *file* named `work` is authored.
    assert "at least one more segment" in section
    assert "workflows/ci.yml" in section
    assert ".work/" in section
    assert "benchmarks/<case>/work/" in section


def test_the_section_disclaims_history_rewriting():
    """`git rm -r --cached` is the remedy the gate asks for. Saying so here is
    what stops a reader escalating a hygiene failure into a history purge."""
    section = _section()

    assert "git rm -r --cached" in section
    assert "history rewrite" in section
