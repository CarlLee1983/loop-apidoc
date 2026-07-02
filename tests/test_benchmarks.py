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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from openapi_spec_validator import validate as validate_openapi

from loop_apidoc.agentcli.assemble import run_assemble_pipeline
from loop_apidoc.foundry.approve import approve_candidate
from loop_apidoc.foundry.importer import import_run
from loop_apidoc.foundry.models import Docset
from loop_apidoc.foundry.query import load_current_asset, resolve_current_artifact
from loop_apidoc.foundry.register import register_docset
from loop_apidoc.score import ScoreProfile, evaluate_score, load_score_inputs

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


def _issue_classes(report) -> dict[str, int]:
    """Full classified issue tally as `{CODE.severity: count}` — the same shape as
    each case's `validation.expect.json.current_issue_classes`. Asserting the whole
    map (not just errors) makes a drift in *warning* counts a real regression signal."""
    counts: Counter[str] = Counter()
    for issue in report.issues:
        counts[f"{issue.code.value}.{issue.severity.value}"] += 1
    return dict(counts)


@pytest.fixture(params=_cases(), ids=[c.name for c in _cases()])
def case(request) -> Path:
    return request.param


# Assemble each case at most once per session; the produced run dir is treated
# read-only by every consumer (score reads it; foundry copytrees FROM it), so a
# single shared run dir is safe. tmp_path_factory is session-scoped, so the dir
# survives for the whole session.
_ASSEMBLED: dict[str, object] = {}


@pytest.fixture
def assembled(case, tmp_path_factory):
    if not _has_sources(case):
        pytest.skip(f"{case.name}: sources/ not present (operator-provided, gitignored)")
    if case.name not in _ASSEMBLED:
        out = tmp_path_factory.mktemp(f"bench-{case.name}")
        _ASSEMBLED[case.name] = run_assemble_pipeline(
            sources_root=case / "sources",
            extraction_dir=case / "extraction",
            output_root=out,
            run_id="bench",
            generated_at=_FIXED_TS,
        )
    return _ASSEMBLED[case.name]


def test_benchmark_case(case, assembled) -> None:
    expect = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))
    minimum = json.loads((case / "expected" / "minimum.json").read_text("utf-8"))
    must = minimum.get("must_have", {})

    result = assembled
    report = result.report

    # --- 1. PASS/FAIL matches expectation ---
    want_pass = expect.get("current_status") == "PASS"
    assert report.ok is want_pass, (
        f"{case.name}: expected ok={want_pass}, got errors="
        f"{[(i.code.value, i.location) for i in report.errors()]}"
    )

    # --- 2. full classified issue map matches (errors AND warnings) ---
    # The whole {CODE.severity: count} map must match the case's declaration, so a
    # drift in warning counts (not just errors) is caught as a regression.
    want_classes = expect.get("current_issue_classes", {}) or {}
    got_classes = _issue_classes(report)
    assert got_classes == want_classes, (
        f"{case.name}: issue-class map drift — expected {want_classes}, got {got_classes} "
        f"(detail: {[(i.code.value, i.severity.value, i.location) for i in report.issues]})"
    )

    # --- 3. OpenAPI 3.1 is structurally valid ---
    doc = yaml.safe_load((Path(result.run_dir) / "openapi.yaml").read_text("utf-8"))
    validate_openapi(doc)
    assert doc.get("openapi", "").startswith("3.1"), f"{case.name}: not OpenAPI 3.1"

    paths = doc.get("paths", {}) or {}
    webhooks = doc.get("webhooks", {}) or {}
    schemas = (doc.get("components", {}) or {}).get("schemas", {}) or {}
    sec = (doc.get("components", {}) or {}).get("securitySchemes", {}) or {}
    servers = doc.get("servers", []) or []

    # --- 4. structural minimums (>= floor; harness must not silently regress) ---
    assert len(paths) >= must.get("endpoints_min", 0), f"{case.name}: too few paths"
    assert len(webhooks) >= must.get("webhooks_min", 0), f"{case.name}: too few webhooks"
    assert len(schemas) >= must.get("schemas_min", 0), f"{case.name}: too few schemas"
    assert len(sec) >= must.get("security_schemes_min", 0), f"{case.name}: too few securitySchemes"
    # base_urls = OpenAPI servers (0 is valid for webhook-only specs, e.g. github/paypal)
    assert len(servers) >= must.get("base_urls", 0), f"{case.name}: too few servers/base URLs"

    # --- 5. critical operations are present (paths.{path}.{method}) ---
    for ref in minimum.get("critical_operations", []):
        body = ref[len("paths."):] if ref.startswith("paths.") else ref
        path, _, method = body.rpartition(".")
        assert path in paths and method in paths[path], (
            f"{case.name}: critical op {ref} missing from OpenAPI paths"
        )

    run_dir = Path(result.run_dir)

    # integration-contract is also where error codes + integration mechanics land;
    # load once (absent for cases with no integration source).
    ic_path = run_dir / "integration-contract.json"
    ic = json.loads(ic_path.read_text("utf-8")) if ic_path.is_file() else {}

    # error-code floor (inventory.errors → integration-contract.error_codes)
    assert len(ic.get("error_codes", [])) >= must.get("error_codes_min", 0), (
        f"{case.name}: too few error codes "
        f"({len(ic.get('error_codes', []))} < {must.get('error_codes_min', 0)})"
    )

    # --- 6. provenance present and covers something ---
    if must.get("provenance"):
        prov = json.loads((run_dir / "provenance.json").read_text("utf-8"))
        entries = prov.get("entries", prov) if isinstance(prov, dict) else prov
        assert entries, f"{case.name}: provenance has no entries"

    # --- 7. examples generated ---
    if must.get("examples"):
        ex = run_dir / "examples"
        assert ex.is_dir() and any(ex.rglob("request.*")), f"{case.name}: no examples generated"

    # --- 8. integration-contract present + meets declared floors ---
    integ = minimum.get("integration", {}) or {}
    if integ.get("required"):
        assert ic_path.is_file(), (
            f"{case.name}: integration required but integration-contract.json missing"
        )
        # crypto/callbacks are asserted only in the positive direction: required=True
        # demands ≥1 entry. required=False does NOT mean empty (e.g. paypal declares
        # callbacks_required=False yet legitimately carries crypto/callbacks).
        if integ.get("crypto_required"):
            assert ic.get("crypto"), f"{case.name}: crypto required but none in integration-contract"
        if integ.get("callbacks_required"):
            assert ic.get("callbacks"), f"{case.name}: callbacks required but none in integration-contract"
        assert len(ic.get("field_conditions", [])) >= integ.get("field_conditions_min", 0), (
            f"{case.name}: too few field_conditions "
            f"({len(ic.get('field_conditions', []))} < {integ.get('field_conditions_min', 0)})"
        )
        assert len(ic.get("test_cases", [])) >= integ.get("test_cases_min", 0), (
            f"{case.name}: too few test_cases "
            f"({len(ic.get('test_cases', []))} < {integ.get('test_cases_min', 0)})"
        )


def test_benchmark_score(case, assembled) -> None:
    """score grades every run dir 0–100, deterministically, without ever changing
    validation pass/fail (the CLAUDE.md invariant). No per-case score floor — a
    validation-PASS case can legitimately score low on completeness warnings."""
    expect = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))
    inputs = load_score_inputs(Path(assembled.run_dir))

    for profile in (ScoreProfile.CI, ScoreProfile.REVIEW):
        report = evaluate_score(inputs, profile=profile)
        assert 0 <= report.score <= 100, f"{case.name}: score {report.score} out of band"
        assert report.profile is profile, f"{case.name}: profile not echoed"
        again = evaluate_score(inputs, profile=profile)
        assert again.score == report.score, f"{case.name}: score not deterministic"

    # Core invariant: scoring does not change the validation verdict.
    want_pass = expect.get("current_status") == "PASS"
    assert assembled.report.ok is want_pass, f"{case.name}: score run perturbed validation ok"


def test_benchmark_foundry(case, assembled, tmp_path) -> None:
    """Full governance chain against a throwaway .foundry/: register → import →
    approve → resolve current. import_run needs only a complete run dir (not a
    PASS), so the EXPECTED_FAIL case imports fine and only approval needs the
    allow_failing override."""
    expect = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))
    want_pass = expect.get("current_status") == "PASS"
    root = tmp_path  # fresh .foundry/, zero pollution

    register_docset(root, Docset(
        docset_id="bench", title=case.name, provider="bench", product="bench",
    ))
    imported = import_run(root, "bench", Path(assembled.run_dir))
    asset = approve_candidate(
        root, "bench", imported.run_id,
        approved_by="bench", now=_FIXED_TS,
        allow_failing=not want_pass,  # EXPECTED_FAIL cases (e.g. paypal) need this
    )

    current = load_current_asset(root, "bench")
    assert current.asset_id == asset.asset_id, f"{case.name}: current pointer != approved asset"
    openapi = resolve_current_artifact(root, "bench", "openapi")
    assert openapi.is_file(), f"{case.name}: current asset openapi artifact missing on disk"


def test_benchmark_harness_discovers_cases() -> None:
    # Guard: the harness itself must keep finding the committed cases (so a broken
    # discovery doesn't make the whole suite silently vacuous).
    names = {c.name for c in _cases()}
    assert {"newebpay-mpg", "apis-guru-baseline", "tappay-backend",
            "line-pay-online-v3", "stripe-basic-rest", "cybersource-payments",
            "github-webhooks", "paypal-webhooks-incomplete",
            "ecpay-creditcard-pdf", "adyen-payments-multimethod"} <= names
