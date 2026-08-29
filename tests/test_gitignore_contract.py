from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import quality_gate


REPO_ROOT = Path(__file__).resolve().parents[1]

# The only ignore files this contract may be satisfied by.
REPO_IGNORE_FILES = (".gitignore", "benchmarks/.gitignore")


def _ignore_match(path: str) -> tuple[str, str] | None:
    """Ask Git itself rather than reimplementing gitignore semantics — the
    pattern language has enough corner cases (anchoring, negation, directory
    vs. file, precedence) that a hand-rolled parser would be the thing under
    test instead of the file.

    Every path passed here must have at least one component *after* the
    directory being tested (`tmp/x.json`, never a bare `tmp`). Git infers
    directory-ness from the path shape for leading components, but stats the
    filesystem for the last one — so a bare name answers "ignored" on a machine
    where the directory happens to exist and "not ignored" on a fresh clone.
    `--no-index` keeps the answer about the pattern files rather than about what
    is currently tracked.

    Returns the winning `(ignore file, pattern)`, or None when nothing matches,
    so a caller can assert *which* rule won — a repo-tracked ignore file, never
    the developer's `core.excludesFile`. The line number is deliberately dropped:
    coupling a test to it would make editing a comment a test failure."""
    result = subprocess.run(
        ["git", "check-ignore", "-v", "--no-index", "--", path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1), (
        f"git check-ignore failed for {path!r}: {result.stderr}"
    )
    if result.returncode == 1:
        return None
    source, _line, rest = result.stdout.split(":", 2)
    pattern = rest.split("\t", 1)[0]
    assert source in REPO_IGNORE_FILES, (
        f"{path!r} is ignored by {source!r}, not by a repo-tracked ignore file; "
        "a developer's global excludes must never satisfy this contract"
    )
    return source, pattern


# Every root but one is anchored. `sources` is the documented exception below.
ANCHORED_ROOTS = tuple(
    root for root in quality_gate.REPOSITORY_HYGIENE_FORBIDDEN_ROOTS if root != "sources"
)


@pytest.mark.parametrize("root", quality_gate.REPOSITORY_HYGIENE_FORBIDDEN_ROOTS)
def test_every_forbidden_root_is_actually_gitignored(root):
    """The gate detects a root that got committed; `.gitignore` is what stops it
    getting committed. Adding a root to the inventory without an ignore entry
    would leave the gate as the only line of defence, failing the contributor at
    commit time instead of preventing the mistake."""
    assert _ignore_match(f"{root}/generated.json") is not None, root


@pytest.mark.parametrize("root", ANCHORED_ROOTS)
def test_anchored_roots_are_anchored_by_pattern_not_only_by_behaviour(root):
    """Assert the winning pattern, so a de-anchoring edit fails on the rule that
    changed rather than only on a downstream consequence."""
    match = _ignore_match(f"{root}/generated.json")

    assert match == (".gitignore", f"/{root}/"), (root, match)


@pytest.mark.parametrize(
    "path",
    [
        "loop_apidoc/tmp/scratch.json",
        "tests/tmp/conftest.py",
        "loop_apidoc/runs/history.json",
        "docs/runs/index.md",
        "loop_apidoc/.loop-apidoc/state.json",
        "loop_apidoc/work/build.json",
        "loop_apidoc/out/result.json",
        "docs/teams-archive-preview/notes.md",
    ],
)
def test_anchored_ignores_do_not_reach_nested_directories(path):
    """`tmp/`, `runs/` and `.loop-apidoc/` were unanchored, so they also ignored
    any same-named directory at any depth. Nothing needed that, and it meant a
    future `loop_apidoc/tmp/` module would vanish from `git add` with no error at
    all — the silent failure this whole boundary exists to prevent. The already-
    anchored roots are covered too, so the property holds for the inventory
    rather than for the three entries one change happened to touch."""
    assert _ignore_match(path) is None, path


def test_sources_stays_unanchored_as_defence_in_depth_for_a_disclosure_root():
    """The one deliberate exception, and the assertion is written so it FAILS if
    someone tidies `sources/` into `/sources/`.

    The reason is *not* that the benchmark snapshots need it — `benchmarks/
    .gitignore`'s `*/sources/` is the rule that actually wins there, verified,
    and anchoring this entry would leave those covered. The reason is that
    operators really do put supplier material in a nested `sources/`: this
    machine has one under each of `work/`, `.work/`, `tmp/`, `.loop-apidoc/` and
    `runs/`. `sources` is a disclosure root, where the failure is a redistribution
    of someone else's document and a later `git rm` does not undo it, so a second
    overlapping rule is cheap insurance rather than redundancy.

    This knowingly costs the anchoring principle one exception: a future
    `loop_apidoc/sources/` module would be ignored silently. That tension is the
    content of the exception, not an oversight — for a disclosure root the
    trade is worth it, and the hygiene gate cannot cover the nested case at all
    because it is root-anchored by design."""
    assert _ignore_match("vendor/acquired/sources/spec.md") == (".gitignore", "sources/")


def test_benchmark_snapshots_are_covered_by_the_benchmark_ignore_file():
    """Prevention does not live in one file. Naming the winning rule here means a
    later edit to `benchmarks/.gitignore` cannot quietly hand the job to the
    root file's exception above."""
    for case in quality_gate.REQUIRED_BENCHMARK_CASES:
        assert _ignore_match(f"benchmarks/{case}/sources/spec.md") == (
            "benchmarks/.gitignore",
            "*/sources/",
        ), case


def test_the_dot_work_rule_survives_the_anchoring_pass():
    """`.work/` predates the hygiene inventory and is not in it; narrowing the
    neighbouring entries must not disturb it."""
    assert _ignore_match(".work/local.json") is not None
    assert _ignore_match("loop_apidoc/.work/local.json") is None
