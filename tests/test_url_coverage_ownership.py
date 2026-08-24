from __future__ import annotations

import ast
from pathlib import Path

from loop_apidoc.url_coverage import UrlCoverage


def test_url_coverage_has_one_neutral_owner() -> None:
    assert UrlCoverage.__module__ == "loop_apidoc.url_coverage"


def test_preparation_coverage_remains_a_compatibility_reexport() -> None:
    from loop_apidoc.preparation.coverage import UrlCoverage as legacy_url_coverage

    assert legacy_url_coverage is UrlCoverage


def test_production_consumers_do_not_depend_on_preparation_coverage() -> None:
    legacy = Path("loop_apidoc/preparation/coverage.py")
    violations: list[str] = []
    for path in Path("loop_apidoc").rglob("*.py"):
        if path == legacy:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "loop_apidoc.preparation.coverage"
            ):
                violations.append(str(path))
    assert violations == []
