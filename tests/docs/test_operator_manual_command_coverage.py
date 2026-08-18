from __future__ import annotations

import re
from pathlib import Path

from tests.cli_commands_support import registered_cli_commands


# `AGENTS.md` names these two files the operator manual — where an operator looks
# a command up. The CLI is its own inventory, so coverage is checked against the
# registered names instead of a hand-kept list: `governance-review-plan` shipped
# in 2026-07 and was missing from both manuals until #135, and nothing would have
# caught the next one either.
MANUALS = (Path("docs/operator-manual.html"), Path("docs/operator-manual.en.html"))

# Commands deliberately left out of the operator manual, each with the reason.
# The list exists so that this test forces a decision rather than a paragraph
# written to make it pass — an invented section is worse than an absent one.
UNDOCUMENTED_COMMANDS: dict[str, str] = {}

# A sub-app documented as one section names its subcommands collectively, e.g.
# `foundry [init|import|approve|list|current]`. That is the manual saying so, not
# an exemption: a new subcommand missing from the brackets still fails, and the
# fix is to widen the brackets.
_GROUPED_FORM = re.compile(r"([a-z][a-z-]*) \[([a-z][a-z|-]*)\]")

# The table of contents is stripped before matching. A one-line anchor there is a
# link to a section, not the section — counting it would let a command satisfy
# this check with no prose at all, which is the paragraph-written-to-pass outcome
# the exclusion list exists to avoid.
_TOC_ENTRY = re.compile(r'<a class="lvl-\d"[^>]*>.*?</a>')


def _documented_commands(manual: Path) -> set[str]:
    text = _TOC_ENTRY.sub("", manual.read_text(encoding="utf-8"))
    documented = {
        f"{group} {name}"
        for group, alternatives in _GROUPED_FORM.findall(text)
        for name in alternatives.split("|")
    }
    # A bounded match, not a substring: `check-freshness` occurs inside
    # `check-freshness-batch`, so plain containment would report a command as
    # documented because a longer one is.
    return documented | {
        command
        for command in registered_cli_commands()
        if re.search(rf"(?<![\w-]){re.escape(command)}(?![\w-])", text)
    }


def test_every_registered_command_is_in_both_operator_manuals():
    expected = registered_cli_commands() - set(UNDOCUMENTED_COMMANDS)

    assert expected, "no commands registered"
    for manual in MANUALS:
        documented = _documented_commands(manual)

        assert expected <= documented, (manual, sorted(expected - documented))


def test_every_exclusion_names_a_live_command_and_a_reason():
    """An exclusion outlives the command it was written for otherwise, and an
    empty reason is the same omission this list was meant to make visible."""
    assert set(UNDOCUMENTED_COMMANDS) <= registered_cli_commands()
    assert all(reason.strip() for reason in UNDOCUMENTED_COMMANDS.values())


def test_the_manuals_document_the_command_this_check_was_written_for():
    """`governance-review-plan` is the gap that prompted the check (#135). Keeping
    it named here means a rewrite that drops the section fails for the original
    reason, not just as one entry in a set difference."""
    for manual in MANUALS:
        assert "governance-review-plan" in manual.read_text(encoding="utf-8"), manual


def test_a_longer_command_name_does_not_document_the_shorter_one(tmp_path):
    """`check-freshness` sits inside `check-freshness-batch`. Reading coverage by
    containment would call the shorter command documented on the strength of the
    longer one — the check would then pass over exactly the gap it looks for."""
    manual = tmp_path / "manual.html"
    manual.write_text("<code>check-freshness-batch</code>", encoding="utf-8")

    documented = _documented_commands(manual)

    assert "check-freshness-batch" in documented
    assert "check-freshness" not in documented
