from __future__ import annotations

import re

# typer.rich_utils sets FORCE_TERMINAL=True whenever GITHUB_ACTIONS / FORCE_COLOR /
# PY_COLORS is present, so CLI output carries ANSI styling on CI but not locally.
# rich's highlighter styles an option's leading dashes separately from its name, which
# splits a literal like "--source-quality" across escape sequences — an assertion on the
# raw output then passes locally and fails on CI. Assert on the stripped text instead.
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Remove ANSI SGR escape sequences so CLI assertions are colour-independent."""
    return _ANSI_ESCAPE.sub("", text)
