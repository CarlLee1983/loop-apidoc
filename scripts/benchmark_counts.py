"""Structural counts of a completed benchmark run, and the recorder that writes
them back into a case's `expected/minimum.json`.

The counting lives here rather than in the test so that recording a snapshot and
asserting against it cannot drift apart: `tests/test_benchmarks.py` imports
`COUNT_KEYS`/`count_run_dir`, and `python scripts/benchmark_counts.py --record`
writes what the same function measured. Hand-editing thirteen JSON files was the
alternative, and one mistyped field there is invisible (#126).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

HTTP_METHODS = frozenset(
    {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
)

COUNT_KEYS = (
    "operations",
    "paths",
    "webhooks",
    "schemas",
    "security_schemes",
    "servers",
    "error_codes",
    "field_conditions",
    "test_cases",
)


def operation_count(paths: dict) -> int:
    """Operations, not paths: `/free-spin` with GET and POST is two."""
    return sum(
        1
        for path_item in paths.values()
        if isinstance(path_item, dict)
        for method in path_item
        if method.lower() in HTTP_METHODS
    )


def count_run_dir(run_dir: Path) -> dict[str, int]:
    """Every counted artifact of one assembled run. Values come from the run's
    own outputs, so a recorded snapshot and a test assertion always measure the
    same thing."""
    document = yaml.safe_load((run_dir / "openapi.yaml").read_text(encoding="utf-8"))
    paths = document.get("paths", {}) or {}
    components = document.get("components", {}) or {}
    contract_path = run_dir / "integration-contract.json"
    contract = (
        json.loads(contract_path.read_text(encoding="utf-8"))
        if contract_path.is_file()
        else {}
    )
    return {
        "operations": operation_count(paths),
        "paths": len(paths),
        "webhooks": len(document.get("webhooks", {}) or {}),
        "schemas": len(components.get("schemas", {}) or {}),
        "security_schemes": len(components.get("securitySchemes", {}) or {}),
        "servers": len(document.get("servers", []) or []),
        "error_codes": len(contract.get("error_codes", []) or []),
        "field_conditions": len(contract.get("field_conditions", []) or []),
        "test_cases": len(contract.get("test_cases", []) or []),
    }


def record_counts(case_dir: Path, counts: dict[str, int]) -> None:
    """Replace one case's `counts` block, leaving every other declaration —
    the case-specific `_note`, presence booleans, critical operations — alone."""
    path = case_dir / "expected" / "minimum.json"
    minimum = json.loads(path.read_text(encoding="utf-8"))
    minimum["counts"] = {key: counts[key] for key in COUNT_KEYS}
    path.write_text(
        json.dumps(minimum, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="benchmark case directory")
    parser.add_argument("--run-dir", required=True, help="an assembled run directory")
    parser.add_argument(
        "--record",
        action="store_true",
        help="write the counts into the case's minimum.json instead of printing them",
    )
    args = parser.parse_args(argv)

    counts = count_run_dir(Path(args.run_dir))
    if args.record:
        record_counts(Path(args.case), counts)
        print(f"recorded {args.case}: {counts}")
    else:
        print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
