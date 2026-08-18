"""Reading the benchmark case count back out of prose.

`scripts/quality_gate.py::REQUIRED_BENCHMARK_CASES` is the machine-readable
truth about which cases the harness contains; the documents are its
human-readable presentation. This module holds only what a test needs to compare
the two — the spelling table, the phrasings that state the *total*, and which
documents are read. Nothing here generates prose (#134).
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


# How each count is spelled in the two languages the documents are written in.
# The table covers 10-20 only: the harness has held between ten and thirteen
# cases and grows one case at a time, so this spans the range in use plus room
# ahead. It is not a general number-to-word converter, and a count that leaves
# the range must extend it — `test_the_current_count_is_inside_the_spelled_range`
# fails loudly rather than letting an unspelled number go unchecked. The lower
# bound is deliberate too: the phrasings below cannot always tell a total from a
# subset, and small numbers are what subsets are written with ("The four cases",
# "5 restored cases"). Extending the table downward would turn those into
# spurious totals, so it must not be done to make an unrelated sentence match.
NUMBER_WORDS: dict[int, tuple[str, ...]] = {
    10: ("ten", "十"),
    11: ("eleven", "十一"),
    12: ("twelve", "十二"),
    13: ("thirteen", "十三"),
    14: ("fourteen", "十四"),
    15: ("fifteen", "十五"),
    16: ("sixteen", "十六"),
    17: ("seventeen", "十七"),
    18: ("eighteen", "十八"),
    19: ("nineteen", "十九"),
    20: ("twenty", "二十"),
}

_WORD_TO_NUMBER = {
    word: number for number, words in NUMBER_WORDS.items() for word in words
}

# Longest first so "十三" is not read as "十", and digits guarded on both sides so
# a group inside a larger number ("1,189") is never mistaken for a count.
_COUNT = r"(?P<count>(?<!\d)\d{1,3}(?!\d)|(?<![A-Za-z])(?:%s)(?![A-Za-z]))" % "|".join(
    sorted(_WORD_TO_NUMBER, key=len, reverse=True)
)

# Each pattern is one way a document states the harness *total*. Counts that name
# a subset ("5 restored cases", "2 source-backed cases", "Nine of the thirteen")
# are deliberately absent: they are a different number and must not be rewritten
# when a case is added. `\s+` spans a line break, so a wrapped phrase still reads.
_TOTAL_COUNT_PHRASINGS = (
    r"{count}-case inventory",
    r"{count}-case regression harness",
    r"{count}\s+(?:committed\s+)?benchmark\s+cases?\b",
    r"{count}\s+unique\s+cases?\b",
    r"{count}\s+unique\s+fixture\s+directories",
    r"{count}\s+required\s+cases?\b",
    r"\ball\s+{count}\s+cases?\b",
    r"\bthe\s+{count}\s+cases?\b",
    r"\ball\s+{count}\s+original\b",
    r"{count}\s+cases,\s+zero\s+skips",
    r"more\s+than\s+{count}\s+pytest\s+items",
    r"current\s+{count}\s+refers\s+to\s+unique\s+case",
    r"{count}\s*個\s*(?:真實廠商\s*case|benchmark\b|唯一\s*case)",
    r"{count}\s*是唯一\s*case",
    r"全部\s*{count}\s*份原始",
)

TOTAL_COUNT_PATTERNS = tuple(
    re.compile(phrasing.replace("{count}", _COUNT), re.IGNORECASE)
    for phrasing in _TOTAL_COUNT_PHRASINGS
)


# Documents that describe the harness as it stands. Every total they state must
# equal the current count.
CURRENT_DOCS = (
    Path("AGENTS.md"),
    Path("README.md"),
    Path("README.en.md"),
    Path("docs/BENCHMARK_VALIDATION_PLAN.md"),
    Path("docs/PRODUCT_EXTENSION_ROADMAP.md"),
    Path("docs/RELEASE_CHECKLIST.md"),
    Path("docs/index.html"),
    Path("docs/index.en.html"),
    Path("docs/introduction.html"),
    Path("docs/introduction.en.html"),
    Path("docs/onboarding.html"),
    Path("docs/onboarding.en.html"),
    Path("docs/operator-manual.html"),
    Path("docs/operator-manual.en.html"),
)

# Documents that record what was true at one point in time: a release note states
# what shipped in that release, and an ADR states what was measured when the
# decision was taken. Editing either to match today's count would falsify the
# record — "measured across all thirteen cases" stays thirteen even after the
# fourteenth case exists, because thirteen is what was measured. They are named
# one by one rather than skipped by a `docs/RELEASE_NOTES_*` glob, so a new
# current document cannot fall out of coverage by where it happens to live. Each
# is pinned to the count it recorded rather than merely excluded: the number is a
# fixed fact, so editing it is the falsification this list exists to prevent.
HISTORICAL_DOCS: dict[Path, int] = {
    Path("docs/RELEASE_NOTES_0.16.0.md"): 13,
    Path("docs/RELEASE_NOTES_0.16.1.md"): 13,
    Path("docs/RELEASE_NOTES_0.22.0.md"): 13,
    Path("docs/RELEASE_NOTES_0.36.0.md"): 13,
    Path("docs/RELEASE_NOTES_0.37.0.md"): 13,
    Path("docs/RELEASE_NOTES_0.38.0.md"): 13,
    Path("docs/adr/0007-source-fact-scanning-stays-limited-to-well-structured-markdown.md"): 13,
    Path("docs/adr/0008-an-unclosed-fence-is-reported-not-guessed-shut.md"): 13,
    Path("docs/adr/0009-the-two-markdown-scanners-stay-separate.md"): 13,
    Path("docs/adr/0011-a-labelled-method-is-a-literal-not-an-inference.md"): 13,
    Path("docs/adr/0012-no-converter-for-legacy-word-or-spreadsheets.md"): 13,
    Path("docs/adr/0013-a-pdf-case-asserts-derivability-not-a-second-pipeline.md"): 13,
}


def spelled(count: int) -> tuple[str, ...]:
    """Every way `count` may appear in prose: the digits, then each language's word."""
    return (str(count),) + NUMBER_WORDS[count]


def stated_counts(path: Path) -> list[tuple[int, str]]:
    """The harness totals a document states, as (number, the phrase that says it)."""
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    stated: list[tuple[int, str]] = []
    for pattern in TOTAL_COUNT_PATTERNS:
        for match in pattern.finditer(text):
            token = match.group("count").lower()
            number = int(token) if token.isdigit() else _WORD_TO_NUMBER[token]
            stated.append((number, " ".join(match.group(0).split())))
    return stated


def docs_stating_a_total() -> list[Path]:
    """Every repository document that states a harness total, found rather than listed."""
    candidates = sorted(
        {
            *REPO_ROOT.glob("*.md"),
            *REPO_ROOT.glob("docs/**/*.md"),
            *REPO_ROOT.glob("docs/**/*.html"),
        }
    )
    return [
        path.relative_to(REPO_ROOT)
        for path in candidates
        if stated_counts(path.relative_to(REPO_ROOT))
    ]
