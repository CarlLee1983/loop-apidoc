from __future__ import annotations

import re
from pathlib import Path

ADR_DIR = Path("docs/adr")
ARCHITECTURE = Path("docs/ARCHITECTURE.md")
SECTION_HEADING = "## 決策邊界"
FALSIFIED_MARKER = "**Falsified if:**"

_BACKTICK_SPAN = re.compile(r"`([^`]+)`")
_ADR_LINK = re.compile(r"\]\(adr/([^)\s]+)\)")


def _adr_files() -> list[Path]:
    return sorted(ADR_DIR.glob("[0-9]*.md"))


def _falsified_paragraph(text: str) -> str:
    """從 `**Falsified if:**` 起算,到下一個空行或檔尾為止。"""
    start = text.index(FALSIFIED_MARKER)
    end = text.find("\n\n", start)
    return text[start:] if end == -1 else text[start:end]


def _is_existing_path(span: str) -> bool:
    candidate = span.strip().rstrip("/")
    if not candidate:
        return False
    try:
        return Path(candidate).exists()
    except OSError:
        return False


def _guarded_paths(adr: Path) -> set[str]:
    paragraph = _falsified_paragraph(adr.read_text(encoding="utf-8"))
    return {
        span.strip()
        for span in _BACKTICK_SPAN.findall(paragraph)
        if _is_existing_path(span)
    }


def _boundary_section() -> str:
    lines = ARCHITECTURE.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line == SECTION_HEADING)
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _boundary_rows() -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in _boundary_section().splitlines():
        link = _ADR_LINK.search(line)
        if not line.startswith("|") or link is None:
            continue
        rows.setdefault(link.group(1), []).extend(
            _BACKTICK_SPAN.findall(line[link.end() :])
        )
    return rows


def test_architecture_has_exactly_one_boundary_section():
    headings = [
        line
        for line in ARCHITECTURE.read_text(encoding="utf-8").splitlines()
        if line.startswith(SECTION_HEADING)
    ]

    assert len(headings) == 1


def test_every_adr_has_exactly_one_boundary_row():
    adr_names = [adr.name for adr in _adr_files()]
    link_counts = {
        name: _boundary_section().count(f"](adr/{name})") for name in adr_names
    }

    missing = [name for name, count in link_counts.items() if count == 0]
    duplicated = [name for name, count in link_counts.items() if count > 1]
    unknown = sorted(set(_boundary_rows()) - set(adr_names))

    assert not missing, f"docs/ARCHITECTURE.md 決策邊界缺少 ADR 的列: {missing}"
    assert not duplicated, f"決策邊界中重複出現的 ADR: {duplicated}"
    assert not unknown, f"決策邊界列出不存在的 ADR: {unknown}"


def test_each_row_lists_exactly_the_guarded_paths_of_its_adr():
    rows = _boundary_rows()

    for adr in _adr_files():
        if adr.name not in rows:
            continue  # 缺列由 test_every_adr_has_exactly_one_boundary_row 回報
        listed = rows[adr.name]
        expected = _guarded_paths(adr)

        assert len(listed) == len(set(listed)), (
            f"{adr.name}: 決策邊界列內路徑重複: {listed}"
        )
        assert set(listed) == expected, (
            f"{adr.name}: 決策邊界列的路徑與 Falsified if 不一致; "
            f"缺少 {sorted(expected - set(listed))}, 多出 {sorted(set(listed) - expected)}"
        )


def test_adr_0002_falsified_paragraph_names_its_enforcement_paths():
    adr = ADR_DIR / "0002-separate-documentary-and-empirical-authority.md"
    paragraph = _falsified_paragraph(adr.read_text(encoding="utf-8"))

    for path in (
        "loop_apidoc/domain/conformance.py",
        "loop_apidoc/core/conformance.py",
        "loop_apidoc/feedback/",
    ):
        assert f"`{path}`" in paragraph
