from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN = {
    "anthropic",
    "httpx",
    "openai",
    "pathlib",
    "requests",
    "sqlalchemy",
    "subprocess",
    "typer",
}


def _forbidden_imports(root: str) -> set[str]:
    found: set[str] = set()
    for path in Path(root).glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            found.update(
                name.split(".", 1)[0]
                for name in names
                if name.split(".", 1)[0] in FORBIDDEN
            )
    return found


def test_core_and_domain_do_not_import_platform_packages():
    assert _forbidden_imports("loop_apidoc/core") == set()
    assert _forbidden_imports("loop_apidoc/domain") == set()


def test_core_does_not_read_the_system_clock_directly():
    violations: list[str] = []
    for path in Path("loop_apidoc/core").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"now", "utcnow"}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "datetime"
            ):
                violations.append(f"{path}:{node.lineno}")
    assert violations == []
