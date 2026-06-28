"""Benchmark regression harness.

Re-runs the deterministic assemble→validate tail over each committed benchmark
case in `benchmarks/<case>/extraction/` and asserts the result against that
case's `expected/{validation.expect.json,minimum.json}`. This turns the
benchmark validation set (docs/BENCHMARK_VALIDATION_PLAN.md) into a repeatable
regression suite so the pipeline fixes the cases surfaced can't silently regress.

Sources are operator-provided and gitignored (some are copyrighted), and the
validator needs the cited sources present in the manifest to mark items verified.
So a case whose `sources/` is absent is SKIPPED (run locally where sources exist);
the committed `extraction/` + `expected/` are enough to define the assertions.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from openapi_spec_validator import validate as validate_openapi

from loop_apidoc.agentcli.assemble import run_assemble_pipeline

_BENCH_ROOT = Path(__file__).resolve().parent.parent / "benchmarks"
_FIXED_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _cases() -> list[Path]:
    if not _BENCH_ROOT.is_dir():
        return []
    return sorted(
        d for d in _BENCH_ROOT.iterdir()
        if (d / "extraction" / "inventory.json").is_file()
        and (d / "expected" / "validation.expect.json").is_file()
    )


def _has_sources(case: Path) -> bool:
    src = case / "sources"
    return src.is_dir() and any(src.iterdir())


def _expected_error_count(expect: dict) -> int:
    classes = expect.get("current_issue_classes", {}) or {}
    return sum(v for k, v in classes.items() if k.endswith(".error"))


@pytest.mark.parametrize("case", _cases(), ids=[c.name for c in _cases()])
def test_benchmark_case(case: Path, tmp_path: Path) -> None:
    if not _has_sources(case):
        pytest.skip(f"{case.name}: sources/ not present (operator-provided, gitignored)")

    expect = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))
    minimum = json.loads((case / "expected" / "minimum.json").read_text("utf-8"))
    must = minimum.get("must_have", {})

    # A malformed committed extraction raises AssembleInputError → the test errors,
    # which is the correct signal (the committed JSON must stay assemble-able).
    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path,
        run_id="bench",
        generated_at=_FIXED_TS,
    )
    report = result.report

    # --- 1. PASS/FAIL matches expectation ---
    want_pass = expect.get("current_status") == "PASS"
    assert report.ok is want_pass, (
        f"{case.name}: expected ok={want_pass}, got errors="
        f"{[(i.code.value, i.location) for i in report.errors()]}"
    )

    # --- 2. error issue count matches (warnings are allowed to drift) ---
    want_errors = _expected_error_count(expect)
    assert len(report.errors()) == want_errors, (
        f"{case.name}: expected {want_errors} error(s), got "
        f"{[(i.code.value, i.location) for i in report.errors()]}"
    )

    # --- 3. OpenAPI 3.1 is structurally valid ---
    doc = yaml.safe_load((Path(result.run_dir) / "openapi.yaml").read_text("utf-8"))
    validate_openapi(doc)
    assert doc.get("openapi", "").startswith("3.1"), f"{case.name}: not OpenAPI 3.1"

    paths = doc.get("paths", {}) or {}
    webhooks = doc.get("webhooks", {}) or {}
    schemas = (doc.get("components", {}) or {}).get("schemas", {}) or {}
    sec = (doc.get("components", {}) or {}).get("securitySchemes", {}) or {}

    # --- 4. structural minimums (>= floor; harness must not silently regress) ---
    assert len(paths) >= must.get("endpoints_min", 0), f"{case.name}: too few paths"
    assert len(webhooks) >= must.get("webhooks_min", 0), f"{case.name}: too few webhooks"
    assert len(schemas) >= must.get("schemas_min", 0), f"{case.name}: too few schemas"
    assert len(sec) >= must.get("security_schemes_min", 0), f"{case.name}: too few securitySchemes"

    # --- 5. critical operations are present (paths.{path}.{method}) ---
    for ref in minimum.get("critical_operations", []):
        body = ref[len("paths."):] if ref.startswith("paths.") else ref
        path, _, method = body.rpartition(".")
        assert path in paths and method in paths[path], (
            f"{case.name}: critical op {ref} missing from OpenAPI paths"
        )

    run_dir = Path(result.run_dir)

    # --- 6. provenance present and covers something ---
    if must.get("provenance"):
        prov = json.loads((run_dir / "provenance.json").read_text("utf-8"))
        entries = prov.get("entries", prov) if isinstance(prov, dict) else prov
        assert entries, f"{case.name}: provenance has no entries"

    # --- 7. examples generated ---
    if must.get("examples"):
        ex = run_dir / "examples"
        assert ex.is_dir() and any(ex.rglob("request.*")), f"{case.name}: no examples generated"

    # --- 8. integration-contract present iff the case declares integration ---
    if (minimum.get("integration", {}) or {}).get("required"):
        assert (run_dir / "integration-contract.json").is_file(), (
            f"{case.name}: integration required but integration-contract.json missing"
        )


def test_benchmark_harness_discovers_cases() -> None:
    # Guard: the harness itself must keep finding the committed cases (so a broken
    # discovery doesn't make the whole suite silently vacuous).
    names = {c.name for c in _cases()}
    assert {"newebpay-mpg", "apis-guru-baseline", "tappay-backend",
            "line-pay-online-v3", "stripe-basic-rest", "cybersource-payments"} <= names
