from __future__ import annotations

import re
from pathlib import Path

from scripts import quality_gate


# The documents are the human-readable presentation of the same grading; the
# registry in `scripts/quality_gate.py` is the machine-readable truth. This test
# keeps the four tables from drifting away from it — it never generates them.
DOCS = (
    (Path("README.md"), "zh"),
    (Path("docs/operator-manual.html"), "zh"),
    (Path("README.en.md"), "en"),
    (Path("docs/operator-manual.en.html"), "en"),
)

TIER_MARKERS = {
    "zh": {
        "來源支撐": "source-backed",
        "未經真實來源驗證": "not validated against a real source",
        "結構上不進 harness": "outside the harness by construction",
    },
    "en": {
        "Source-backed": "source-backed",
        "Not validated against a real source": "not validated against a real source",
        "Outside the harness by construction": "outside the harness by construction",
    },
}

# Markdown backticks and the HTML manuals' <code> spans, read the same way.
_CODE_SPAN = re.compile(r"`([^`\n]+)`|<code>([^<\n]+)</code>")


# The tables name one branch by its file extension rather than by the command
# that handles it — "`.docx` preprocessing" is `preprocess`'s second row. Without
# this, the un-validated half of a two-tier command would read as undocumented.
CODE_SPAN_ALIASES = {".docx": "preprocess"}


def _table_rows(path: Path) -> list[str]:
    """Only the grading tables — Markdown pipe rows and HTML `<tr>`s. The
    surrounding prose is deliberately out of scope: it repeats and elaborates
    the labels in sentences no parser should be grading."""
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("|") or "<tr>" in line
    ]


def _documented_tiers(path: Path, language: str) -> dict[str, set[str]]:
    """Command → every tier the document's table puts it in. Rows are located
    by their tier label; spans naming neither a graded command nor an alias are
    ignored."""
    graded = set(quality_gate.SOURCE_ACQUISITION_EVIDENCE_TIERS)
    documented: dict[str, set[str]] = {}
    graded_rows = 0
    for line in _table_rows(path):
        tiers = {
            tier for marker, tier in TIER_MARKERS[language].items() if marker in line
        }
        if len(tiers) != 1:
            continue
        graded_rows += 1
        tier = tiers.pop()
        for markdown, html in _CODE_SPAN.findall(line):
            span = markdown or html
            command = CODE_SPAN_ALIASES.get(span, span)
            if command in graded:
                documented.setdefault(command, set()).add(tier)

    # A reworded or merged row would otherwise vanish from `documented` and
    # could be masked by the same command appearing in another row.
    assert graded_rows == len(quality_gate.ACQUISITION_EVIDENCE_TIERS), path
    return documented


def test_documented_tables_match_the_controlled_list():
    registry = quality_gate.SOURCE_ACQUISITION_EVIDENCE_TIERS
    for path, language in DOCS:
        documented = _documented_tiers(path, language)

        assert set(documented) == set(registry), path
        for command, tiers in documented.items():
            assert tiers == set(registry[command]), (path, command)


def test_documents_do_not_grade_an_excluded_command():
    excluded = set(quality_gate.NON_ACQUISITION_CLI_COMMANDS)
    for path, language in DOCS:
        for line in _table_rows(path):
            if not any(marker in line for marker in TIER_MARKERS[language]):
                continue
            named = {markdown or html for markdown, html in _CODE_SPAN.findall(line)}

            assert named & excluded == set(), (path, named & excluded)
