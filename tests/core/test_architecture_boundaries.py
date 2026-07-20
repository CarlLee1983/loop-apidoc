from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN = {
    "anthropic",
    "fitz",
    "httpx",
    "io",
    "os",
    "openai",
    "pathlib",
    "pymupdf",
    "requests",
    "socket",
    "sqlalchemy",
    "subprocess",
    "typer",
    "urllib",
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


def test_core_and_domain_do_not_call_direct_io_apis():
    violations: list[str] = []
    forbidden_attributes = {
        "open",
        "read_bytes",
        "read_text",
        "write_bytes",
        "write_text",
        "request",
        "get",
        "post",
    }
    for root in ("loop_apidoc/core", "loop_apidoc/domain"):
        for path in Path(root).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id == "open":
                        violations.append(f"{path}:{node.lineno}:open")
                elif isinstance(node, ast.Call) and isinstance(
                    node.func, ast.Attribute
                ):
                    if node.func.attr in forbidden_attributes and isinstance(
                        node.func.value, ast.Name
                    ) and node.func.value.id in {
                        "Path",
                        "httpx",
                        "requests",
                        "socket",
                    }:
                        violations.append(
                            f"{path}:{node.lineno}:{node.func.value.id}.{node.func.attr}"
                        )
    assert violations == []
