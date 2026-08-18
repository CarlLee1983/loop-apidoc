from __future__ import annotations

from scripts import quality_gate
from tests import benchmark_case_count_support as support


# `REQUIRED_BENCHMARK_CASES` is the list; its length is a second fact written out
# by hand in fourteen documents. A literal assertion ("thirteen unique cases" is
# in the text) stays green after the fourteenth case is added and pins the wrong
# word in place, so the number is read back and compared instead (#134).
CURRENT_COUNT = len(quality_gate.REQUIRED_BENCHMARK_CASES)


def test_the_current_count_is_inside_the_spelled_range():
    """The spelling table covers 10-20. A count outside it cannot be checked in
    prose at all, so the table must be extended before the case is added."""
    assert min(support.NUMBER_WORDS) <= CURRENT_COUNT <= max(support.NUMBER_WORDS)


def test_current_docs_state_the_current_count():
    for path in support.CURRENT_DOCS:
        stated = support.stated_counts(path)

        assert stated, f"{path} no longer states the case count"
        for number, phrase in stated:
            assert number == CURRENT_COUNT, (path, phrase)


def test_historical_docs_are_left_at_the_count_they_recorded():
    """A release note records what shipped and an ADR records what was measured;
    both are excluded from the check by name. They are asserted to still state a
    count so the exclusion list cannot quietly outlive its reason."""
    for path in support.HISTORICAL_DOCS:
        assert support.stated_counts(path), f"{path} no longer states a count"


def test_every_document_stating_the_count_is_accounted_for():
    """The registries are checked against a scan, not trusted: a new document
    that states the total must be classified as current or historical, and a
    `docs/RELEASE_NOTES_*` glob would have swallowed a new current document."""
    registered = {*support.CURRENT_DOCS, *support.HISTORICAL_DOCS}

    assert set(support.docs_stating_a_total()) == registered
