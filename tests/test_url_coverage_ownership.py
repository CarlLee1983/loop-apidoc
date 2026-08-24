from __future__ import annotations

import ast
from pathlib import Path

from loop_apidoc.preparation.coverage import UrlCoverage as LegacyUrlCoverage


def test_url_coverage_is_neutral_with_a_legacy_compatibility_export() -> None:
    from loop_apidoc.url_coverage import UrlCoverage

    assert UrlCoverage is LegacyUrlCoverage


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
