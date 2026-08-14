"""`not_found` 必須交代每一份可讀來源。

沒有這道檢查,agent 討好指令最省力的方式就是瞄一眼某份檔案就回報「找不到」——
而那份回答與真正掃過全部來源的回答在輸出上無法區分。宣稱的內容是「它不在任何
一份裡」,列一份來源證明不了那件事。
"""
from __future__ import annotations

from tests.focus.support import (
    assemble,
    directive,
    not_found,
    response,
    setup,
    verify,
)

_EXTRA = {"appendix.md": "# Appendix\nNothing here\n"}
_NOISE = {"logo.png": b"\x89PNG\r\n", "README.md": "# Readme\n"}


def test_listing_every_readable_source_is_accepted(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()],
        responses=[not_found(searched_sources=["manual.md", "appendix.md"])],
        extra_sources=_EXTRA)

    res = verify(sources, extraction, focus)

    assert res.exit_code == 0, res.output


def test_omitting_a_readable_source_is_rejected(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()],
        responses=[not_found(searched_sources=["manual.md"])],
        extra_sources=_EXTRA)

    res = verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "appendix.md" in res.output


def test_the_violation_names_only_the_sources_that_were_missing(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()],
        responses=[not_found(searched_sources=[])],
        extra_sources=_EXTRA)

    res = verify(sources, extraction, focus)

    assert "manual.md" in res.output
    assert "appendix.md" in res.output


def test_naming_a_source_outside_the_manifest_is_rejected(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()],
        responses=[not_found(
            searched_sources=["manual.md", "appendix.md", "ghost.md"])],
        extra_sources=_EXTRA)

    res = verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "ghost.md" in res.output


def test_unreadable_sources_are_neither_required_nor_rejected(tmp_path):
    # logo.png 是 unsupported、README.md 是 ignored:agent 讀不到它們,不能
    # 要求它列出;但列了也不該被當成「manifest 以外的來源」而報錯。
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()],
        responses=[not_found(searched_sources=[
            "manual.md", "appendix.md", "logo.png"])],
        extra_sources={**_EXTRA, **_NOISE})

    res = verify(sources, extraction, focus)

    assert res.exit_code == 0, res.output


def test_a_coverage_directive_is_held_to_the_same_standard(tmp_path):
    # kind 降低的是結局的 severity,不是達成那個結局所需的答案品質。
    sources, extraction, focus = setup(
        tmp_path, directives=[directive(kind="coverage")],
        responses=[not_found(searched_sources=["manual.md"])],
        extra_sources=_EXTRA)

    res = verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "appendix.md" in res.output


def test_a_satisfied_response_needs_no_searched_source_list(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()], responses=[response()],
        extra_sources=_EXTRA)

    res = verify(sources, extraction, focus)

    assert res.exit_code == 0, res.output


def test_assemble_rejects_it_too_and_creates_no_run_directory(tmp_path):
    sources, extraction, focus = setup(
        tmp_path, directives=[directive()],
        responses=[not_found(searched_sources=["manual.md"])],
        extra_sources=_EXTRA)

    res = assemble(tmp_path, sources, extraction, focus)

    assert res.exit_code == 2
    assert "appendix.md" in res.output
    assert not (tmp_path / "runs").exists()
