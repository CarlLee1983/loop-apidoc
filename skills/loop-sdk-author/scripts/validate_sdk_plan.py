#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL = {
    "version",
    "source_run_dir",
    "contracts",
    "runtime",
    "operation_groups",
    "operations",
    "mechanisms",
    "adapters",
    "gaps",
}

REQUIRED_CONTRACTS = {"openapi", "integration", "sdk_hints"}
REQUIRED_OPERATION_FIELDS = {"operation_id", "method", "contract_pointer", "sdk_method"}

FORBIDDEN_KEYS = {
    "framework",
    "app_stack",
    "ui_framework",
    "web_framework",
    "database",
    "orm",
    "controller",
    "middleware",
    "route",
    "component",
    "requestbody",
    "responses",
    "components",
    "schemas",
    "properties",
}

FORBIDDEN_TERMS = [
    "React",
    "Next.js",
    "Vue",
    "Angular",
    "Nuxt",
    "SvelteKit",
    "Django",
    "FastAPI",
    "Flask",
    "Laravel",
    "Rails",
    "Spring Boot",
    "NestJS",
    "Remix",
]


def _path(parts: list[str]) -> str:
    return "$" + "".join(parts)


def _key_token(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", key.lower())


def _walk_forbidden(node: Any, parts: list[str], errors: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = [*parts, f".{key}"]
            if _key_token(key) in FORBIDDEN_KEYS:
                errors.append(f"{_path(child_path)} uses forbidden key {key!r}")
            _walk_forbidden(value, child_path, errors)
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            _walk_forbidden(value, [*parts, f"[{idx}]"], errors)
    elif isinstance(node, str):
        lowered = node.lower()
        for term in FORBIDDEN_TERMS:
            if term.lower() in lowered:
                errors.append(f"{_path(parts)} mentions forbidden app framework {term!r}")


def _expect_object(name: str, value: Any, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"$.{name} must be an object")
        return None
    return value


def _expect_list(name: str, value: Any, errors: list[str]) -> list[Any] | None:
    if not isinstance(value, list):
        errors.append(f"$.{name} must be a list")
        return None
    return value


def validate(plan: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["$ must be a JSON object"]

    missing = sorted(REQUIRED_TOP_LEVEL - set(plan))
    for key in missing:
        errors.append(f"$.{key} is required")

    if plan.get("version") != "1.0":
        errors.append("$.version must be '1.0'")

    contracts = _expect_object("contracts", plan.get("contracts"), errors)
    if contracts is not None:
        for key in sorted(REQUIRED_CONTRACTS - set(contracts)):
            errors.append(f"$.contracts.{key} is required")

    runtime = _expect_object("runtime", plan.get("runtime"), errors)
    if runtime is not None:
        _expect_list("runtime.config", runtime.get("config"), errors)

    _expect_list("operation_groups", plan.get("operation_groups"), errors)
    _expect_object("mechanisms", plan.get("mechanisms"), errors)
    _expect_list("adapters", plan.get("adapters"), errors)
    _expect_list("gaps", plan.get("gaps"), errors)

    operations = _expect_list("operations", plan.get("operations"), errors)
    if operations is not None:
        for idx, op in enumerate(operations):
            if not isinstance(op, dict):
                errors.append(f"$.operations[{idx}] must be an object")
                continue
            for key in sorted(REQUIRED_OPERATION_FIELDS - set(op)):
                errors.append(f"$.operations[{idx}].{key} is required")
            pointer = op.get("contract_pointer")
            if isinstance(pointer, str) and not pointer.startswith("../openapi.yaml#"):
                errors.append(
                    f"$.operations[{idx}].contract_pointer must point into ../openapi.yaml"
                )

    _walk_forbidden(plan, [], errors)
    return errors


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a loop-sdk-author sdk-plan.json.")
    parser.add_argument("plan", type=Path, help="Path to sdk-plan.json")
    args = parser.parse_args(argv)

    try:
        plan = load_json(args.plan)
    except OSError as exc:
        print(f"ERROR: cannot read {args.plan}: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in {args.plan}: {exc}", file=sys.stderr)
        return 2

    errors = validate(plan)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {args.plan} is a stack-neutral SDK plan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
