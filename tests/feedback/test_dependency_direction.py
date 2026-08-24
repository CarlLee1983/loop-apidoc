from __future__ import annotations

import ast
from pathlib import Path


def _imports(path: Path) -> set[str]:
    modules: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
            if node.level >= 2:
                modules.update(alias.name for alias in node.names)
    return modules


def test_foundry_does_not_depend_on_feedback_or_review_layers() -> None:
    forbidden = {"feedback", "review"}
    violations: list[str] = []
    for path in Path("loop_apidoc/foundry").rglob("*.py"):
        for imported in _imports(path):
            if imported in forbidden or imported.startswith(
                ("loop_apidoc.feedback", "loop_apidoc.review")
            ):
                violations.append(f"{path}:{imported}")
    assert violations == []


def test_foundry_package_facade_keeps_operational_imports_lazy() -> None:
    imports = _imports(Path("loop_apidoc/foundry/__init__.py"))
    eager = {
        imported
        for imported in imports
        if imported
        in {
            "approve",
            "feedback",
            "importer",
            "query",
            "register",
            "loop_apidoc.foundry.approve",
            "loop_apidoc.foundry.feedback",
            "loop_apidoc.foundry.importer",
            "loop_apidoc.foundry.query",
            "loop_apidoc.foundry.register",
        }
    }
    assert eager == set()


def test_feedback_workflow_has_no_cli_report_or_loader_dependency() -> None:
    imports = _imports(Path("loop_apidoc/feedback/workflow.py"))
    forbidden = {
        "typer",
        "loop_apidoc.feedback.cli",
        "loop_apidoc.feedback.loader",
        "loop_apidoc.feedback.report",
    }
    assert imports.isdisjoint(forbidden)
