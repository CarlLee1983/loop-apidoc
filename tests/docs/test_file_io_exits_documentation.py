from __future__ import annotations

from pathlib import Path

from scripts import quality_gate


AGENTS = Path(__file__).resolve().parents[2] / "AGENTS.md"
MARKER = "**File-I/O exits**"


def _paragraph() -> str:
    for block in AGENTS.read_text(encoding="utf-8").split("\n\n"):
        if MARKER in block:
            return block
    raise AssertionError(f"{MARKER} paragraph not found in {AGENTS}")


def test_the_purity_claim_points_at_the_enforced_inventory():
    """The paragraph may keep its "every other module is pure" claim only while
    it says where that claim is checked — an unbacked exhaustiveness claim in
    prose is what let ten writers accumulate outside it (#125)."""
    paragraph = _paragraph()

    assert "pure function" in paragraph
    assert "FILE_IO_EXIT_MODULES" in paragraph
    assert "test_every_module_that_writes_is_in_the_file_io_inventory" in paragraph


def test_the_writer_count_in_the_prose_matches_the_inventory():
    """The paragraph states how many writers the purity claim covers. An
    unchecked count in prose is the same failure the ticket was filed about, one
    order smaller."""
    assert str(len(quality_gate.FILE_IO_EXIT_MODULES)) in _paragraph()


def test_the_inventory_is_reachable_from_the_repository_guidance():
    """A reader who follows the paragraph must land on something runnable: the
    file that holds the inventory, not just the constant's name."""
    paragraph = _paragraph()

    assert "scripts/quality_gate.py" in paragraph
    assert len(quality_gate.FILE_IO_EXIT_MODULES) > 0, "inventory is empty"
