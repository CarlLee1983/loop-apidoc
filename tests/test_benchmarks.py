"""Benchmark regression harness.

Re-runs the deterministic assemble→validate tail over each committed benchmark
case in `benchmarks/<case>/extraction/` and asserts the result against that
case's `expected/{validation.expect.json,minimum.json}`. This turns the
benchmark validation set (docs/BENCHMARK_VALIDATION_PLAN.md) into a repeatable
regression suite so the pipeline fixes the cases surfaced can't silently regress.

Sources and their current passing source-quality package are operator-provided and
gitignored (some sources are copyrighted). The validator needs the cited sources in
the manifest and assembly requires the audited package, so a case missing either is
SKIPPED (run locally where both are available); the committed `extraction/` +
`expected/` are enough to define the assertions.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from openapi_spec_validator import validate as validate_openapi

from scripts.benchmark_counts import COUNT_KEYS, count_run_dir, operation_count

from loop_apidoc.agentcli.assemble import run_assemble_pipeline as _run_assemble_pipeline
from loop_apidoc.agentcli.preprocess import prepare_markdown
from loop_apidoc.agentcli.verify import verify_extraction_dir
from loop_apidoc.diff import DiffImpact, build_diff_report, load_run_artifacts
from loop_apidoc.foundry import store as foundry_store
from loop_apidoc.foundry.approve import approve_candidate
from loop_apidoc.foundry.importer import import_run
from loop_apidoc.foundry.models import AssetStatus, Docset, FoundryApprovalError
from loop_apidoc.foundry.query import load_current_asset, resolve_current_artifact
from loop_apidoc.foundry.register import register_docset
from loop_apidoc.preparation import PreparationReport, PreparationSeverity, PreparationStatus
from loop_apidoc.run.models import RunResult
from loop_apidoc.shadow.models import ArchitectureMode
from loop_apidoc.score import (
    LoopVerdict,
    ScoreProfile,
    classify_findings,
    evaluate_score,
    load_score_inputs,
    loop_verdict,
    write_reports as write_score_reports,
)
from scripts.quality_gate import (
    required_sanitized_benchmark_cases,
    required_source_derivation_benchmark_cases,
)

_BENCH_ROOT = Path(__file__).resolve().parent.parent / "benchmarks"
_FIXED_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def run_assemble_pipeline(**kwargs) -> RunResult:
    """Run benchmark assembly with its explicit, current quality prerequisite."""
    source_quality_dir = kwargs["sources_root"].parent / "source-quality"
    if not (source_quality_dir / "source-quality-report.json").is_file():
        raise AssertionError(
            "source-backed benchmark needs its explicit source-quality package"
        )
    kwargs["source_quality_dir"] = source_quality_dir
    return _run_assemble_pipeline(**kwargs)


# Counting lives in scripts/benchmark_counts.py so that recording a snapshot
# and asserting against it cannot measure different things (#126).
_operation_count = operation_count


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
    return (
        src.is_dir()
        and any(src.iterdir())
        and (case / "source-quality" / "source-quality-report.json").is_file()
        and (case / "source-quality" / "source-diff.json").is_file()
    )


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


_STRIPE = "stripe-basic-rest"


def _case_by_name(name: str) -> Path:
    return _BENCH_ROOT / name


def test_jili_case_has_declared_legacy_pdf_counts():
    case = _case_by_name("jili-legacy-gaming-pdf")
    minimum = json.loads((case / "expected" / "minimum.json").read_text("utf-8"))
    assert minimum["counts"]["operations"] == 25
    assert minimum["counts"]["paths"] == 20
    assert "paths./CreateFreeSpin.get" in minimum["critical_operations"]
    assert "paths./CreateFreeSpin.post" in minimum["critical_operations"]


def test_operation_count_counts_methods_separately_from_paths():
    paths = {"/free-spin": {"get": {}, "post": {}}}

    assert len(paths) == 1
    assert _operation_count(paths) == 2


def _assemble_case(case: Path, tmp_path_factory) -> RunResult:
    """Assemble a case at most once per session and memoize the RunResult.

    Skips when the case's operator-provided sources or explicit quality package are absent. The produced run
    dir is treated read-only by every consumer (score reads it; foundry/diff
    copytree FROM it), so a single shared dir is safe. Non-parametrized tests
    reuse this same helper via `_case_by_name` so they never re-assemble."""
    if not _has_sources(case):
        pytest.skip(
            f"{case.name}: sources/ or valid source-quality package not present "
            "(operator-provided, gitignored)"
        )
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


# Assemble each case at most once per session; the produced run dir is treated
# read-only by every consumer (score reads it; foundry copytrees FROM it), so a
# single shared run dir is safe. tmp_path_factory is session-scoped, so the dir
# survives for the whole session.
_ASSEMBLED: dict[str, RunResult] = {}


@pytest.fixture
def assembled(case, tmp_path_factory):
    return _assemble_case(case, tmp_path_factory)


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

    # --- 4. every counted artifact matches the recorded snapshot exactly ---
    # These were `>=` floors until #126. A floor answers "did we clear a number
    # somebody wrote down in 2026-06", not "did the extraction change": newebpay
    # produced 127 error codes against a floor of 80, so losing 47 of them was a
    # silent pass. Equality makes any movement show up in the diff, where it is
    # either an improvement to re-record or the regression the harness exists for.
    assert "counts" in minimum, f"{case.name}: minimum.json has no counts snapshot"
    counts = minimum["counts"]
    assert set(counts) == set(COUNT_KEYS), (
        f"{case.name}: counts keys drifted — recorded {sorted(counts)}, "
        f"expected {sorted(COUNT_KEYS)}"
    )
    got_counts = count_run_dir(Path(result.run_dir))
    assert got_counts == counts, (
        f"{case.name}: counts moved — recorded {counts}, got {got_counts}"
    )

    # --- 5. critical operations are present (paths.{path}.{method}) ---
    for ref in minimum.get("critical_operations", []):
        body = ref[len("paths."):] if ref.startswith("paths.") else ref
        path, _, method = body.rpartition(".")
        assert path in paths and method in paths[path], (
            f"{case.name}: critical op {ref} missing from OpenAPI paths"
        )

    # --- 6. every critical security scheme is present, by identity ---
    # `counts.security_schemes` guards the cardinality only: rename `bearerAuth`
    # to anything and the count is still 2. The declaration now names the emitted
    # `components.securitySchemes` key, so the scheme a case cannot ship without
    # is checked by identity (#137). The prose that used to sit in this key lives
    # in `critical_security_scheme_labels`, which nothing matches against.
    schemes = (doc.get("components") or {}).get("securitySchemes") or {}
    for name in minimum.get("critical_security_schemes", []):
        assert name in schemes, (
            f"{case.name}: critical security scheme {name} missing from OpenAPI "
            f"components.securitySchemes (got {sorted(schemes)})"
        )

    run_dir = Path(result.run_dir)

    # integration-contract is also where error codes + integration mechanics land;
    # load once (absent for cases with no integration source).
    ic_path = run_dir / "integration-contract.json"
    ic = json.loads(ic_path.read_text("utf-8")) if ic_path.is_file() else {}

    # --- 7. provenance present and covers something ---
    if must.get("provenance"):
        prov = json.loads((run_dir / "provenance.json").read_text("utf-8"))
        entries = prov.get("entries", prov) if isinstance(prov, dict) else prov
        assert entries, f"{case.name}: provenance has no entries"

    # --- 8. examples generated ---
    if must.get("examples"):
        ex = run_dir / "examples"
        assert ex.is_dir() and any(ex.rglob("request.*")), f"{case.name}: no examples generated"

    # --- 9. integration-contract present + declared mechanics carried ---
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


def test_benchmark_score(case, assembled) -> None:
    """score grades every run dir 0–100, deterministically, without ever changing
    validation pass/fail (the CLAUDE.md invariant). No per-case score floor — a
    validation-PASS case can legitimately score low on completeness warnings."""
    expect = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))
    run_dir = Path(assembled.run_dir)
    inputs = load_score_inputs(run_dir)

    for profile in (ScoreProfile.CI, ScoreProfile.REVIEW):
        report = evaluate_score(inputs, profile=profile)
        # The 0–100 band is guaranteed by ScoreReport.score = Field(ge=0, le=100):
        # an out-of-band value raises inside evaluate_score before it returns, so a
        # band assert here can never fire. Assert the things the model does NOT
        # enforce instead — the profile echo and cross-load determinism.
        assert report.profile is profile, f"{case.name}: profile not echoed"
        # Determinism across a FRESH load of the run dir, not just a second call on
        # the same inputs object — this also catches nondeterminism leaking in from
        # I/O / dict-or-set ordering during loading, not only from the pure scorer.
        again = evaluate_score(load_score_inputs(run_dir), profile=profile)
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
            "ecpay-creditcard-pdf", "adyen-payments-multimethod",
            "jili-legacy-gaming-pdf", "funkygames-transfer-operator",
            "rsg-game-transfer-wallet"} <= names


# Every key a `minimum.json` may carry. A declaration that reaches the harness
# only through `minimum.get(...)` disappears silently when its key is misspelled,
# which is the shape #137 was filed about one level up.
_MINIMUM_KEYS = {
    "_note",
    "counts",
    "critical_operations",
    "critical_security_schemes",
    "critical_security_scheme_labels",
    "integration",
    "must_have",
}

# The cases whose declaration is load-bearing. It cannot be derived from
# `counts.security_schemes`: jili emits a scheme and deliberately declares none,
# so a derived rule would either force a declaration nobody wants or accept an
# empty one from the seven that need it.
_CASES_DECLARING_SECURITY_SCHEMES = frozenset({
    "adyen-payments-multimethod",
    "cybersource-payments",
    "line-pay-online-v3",
    "newebpay-mpg",
    "rsg-game-transfer-wallet",
    "stripe-basic-rest",
    "tappay-backend",
})


def test_benchmark_cases_declare_security_schemes_by_identity(case) -> None:
    """The declaration's shape, checked without source snapshots.

    The identity check itself needs the assembled OpenAPI and so runs only where
    sources are present; this half is pure data, and CI is exactly where a
    misspelled key or an emptied list would otherwise pass unnoticed.
    """
    minimum = json.loads((case / "expected" / "minimum.json").read_text("utf-8"))

    assert set(minimum) <= _MINIMUM_KEYS, (
        f"{case.name}: unknown minimum.json key(s) {sorted(set(minimum) - _MINIMUM_KEYS)} "
        "— a key the harness does not read is a declaration that cannot fail"
    )

    declared = minimum.get("critical_security_schemes", [])
    if case.name in _CASES_DECLARING_SECURITY_SCHEMES:
        assert declared, f"{case.name}: critical_security_schemes went missing or empty"
    labels = minimum.get("critical_security_scheme_labels", {})

    assert set(labels) <= set(declared), (
        f"{case.name}: a human-readable label names a scheme the case does not "
        f"require: {sorted(set(labels) - set(declared))}"
    )
    assert all(label.strip() for label in labels.values()), (
        f"{case.name}: a blank label documents nothing"
    )


def test_benchmark_cases_declare_core_parity_contract(case) -> None:
    """Every committed case declares the strict-local Core cutover contract.

    This declaration is intentionally checked without source snapshots.  It
    prevents a newly committed benchmark from silently bypassing the later
    source-backed Core/legacy comparison merely because its private snapshot is
    unavailable in CI.
    """
    parity_path = case / "expected" / "core-parity.json"
    assert parity_path.is_file(), f"{case.name}: missing expected/core-parity.json"

    parity = json.loads(parity_path.read_text("utf-8"))
    legacy = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))

    assert parity == {
        "schema_version": 1,
        "expected_legacy_status": legacy["current_status"],
        "expected_core_verdict": (
            "accept" if legacy["current_status"] == "PASS" else "reject"
        ),
        "require_verdict_match": True,
        "require_exact_evidence_for_all_material_claims": True,
        "allowed_semantic_differences": [],
    }


def test_funkygames_exact_openapi_evidence_reaches_core_derivation(
    tmp_path_factory,
) -> None:
    """The retained Funky source snapshot proves v1 pointer evidence end to end."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-core-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    derived_paths = {
        relationship["claim_path"]
        for relationship in relationships
        if relationship["claim_identity"]
        == (
            "claim:operation:POST "
            "/{funkyUrl}/Funky/Game/GetGameList:definition"
        )
        and relationship["relationship"] == "derived_support"
    }

    assert {
        "/method",
        "/path",
        "/responses/200/status_code",
        "/responses/200/schema_ref",
    } <= derived_paths


def test_funkygames_all_operations_have_exact_method_and_path_derivations(
    tmp_path_factory,
) -> None:
    """All 27 retained Swagger operations have v1 method/path evidence.

    This asserts the public shadow-assembly outcome, rather than the internal
    bridge implementation: every source operation must arrive at Core as two
    independently re-computable derived claims.
    """
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-all-operations-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    method_and_path = [
        relationship
        for relationship in relationships
        if relationship["claim_identity"].startswith("claim:operation:")
        and relationship["claim_path"] in {"/method", "/path"}
        and relationship["relationship"] == "derived_support"
    ]
    operation_claims = {relationship["claim_identity"] for relationship in method_and_path}

    assert len(operation_claims) == 27
    assert len(method_and_path) == 54


def test_funkygames_all_documented_response_statuses_have_derivations(
    tmp_path_factory,
) -> None:
    """Each retained operation's documented 200 response reaches Core exactly."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-response-status-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    status_claims = {
        relationship["claim_identity"]
        for relationship in relationships
        if relationship["claim_identity"].startswith("claim:operation:")
        and relationship["claim_path"] == "/responses/200/status_code"
        and relationship["relationship"] == "derived_support"
    }

    assert len(status_claims) == 27


def test_funkygames_all_documented_response_schemas_have_derivations(
    tmp_path_factory,
) -> None:
    """Every source response with a local schema ref reaches Core exactly."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-response-schema-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    schema_claims = {
        relationship["claim_identity"]
        for relationship in relationships
        if relationship["claim_identity"].startswith("claim:operation:")
        and relationship["claim_path"] == "/responses/200/schema_ref"
        and relationship["relationship"] == "derived_support"
    }

    assert len(schema_claims) == 25


def test_funkygames_all_documented_response_descriptions_have_exact_support(
    tmp_path_factory,
) -> None:
    """All 27 source response descriptions are explicit Core support."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-response-description-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    description_claims = {
        relationship["claim_identity"]
        for relationship in relationships
        if relationship["claim_identity"].startswith("claim:operation:")
        and relationship["claim_path"] == "/responses/200/description"
        and relationship["relationship"] == "explicit_support"
    }

    assert len(description_claims) == 27


def test_funkygames_all_source_summaries_have_exact_support(tmp_path_factory) -> None:
    """Operation summaries use their source scalar, not an operation object."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-summary-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    summaries = [
        relationship
        for relationship in relationships
        if relationship["claim_identity"].startswith("claim:operation:")
        and relationship["claim_path"] == "/summary"
    ]

    assert sum(
        relationship["relationship"] == "explicit_support" for relationship in summaries
    ) == 27
    assert not any(
        relationship["relationship"] == "contradicts" for relationship in summaries
    )


def test_funkygames_direct_parameter_names_have_exact_support(tmp_path_factory) -> None:
    """Only names declared directly on operation parameters become support."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-parameter-names-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    name_claims = [
        relationship
        for relationship in relationships
        if relationship["claim_identity"].startswith("claim:operation:")
        and relationship["claim_path"].startswith("/parameters/")
        and relationship["claim_path"].endswith("/name")
    ]

    assert sum(
        relationship["relationship"] == "explicit_support" for relationship in name_claims
    ) == 104
    assert not any(
        relationship["relationship"] == "contradicts" for relationship in name_claims
    )


def test_funkygames_explicit_parameter_required_values_have_exact_support(
    tmp_path_factory,
) -> None:
    """Only source-explicit operation parameter required flags become support."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-parameter-required-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    required_claims = [
        relationship
        for relationship in relationships
        if relationship["claim_identity"].startswith("claim:operation:")
        and relationship["claim_path"].startswith("/parameters/")
        and relationship["claim_path"].endswith("/required")
    ]

    assert sum(
        relationship["relationship"] == "explicit_support"
        for relationship in required_claims
    ) == 103
    assert not any(
        relationship["relationship"] == "contradicts" for relationship in required_claims
    )


def test_funkygames_direct_body_required_values_have_derivations(
    tmp_path_factory,
) -> None:
    """Direct request-schema fields retain source-stated required flags in Core."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-body-required-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    required_claims = {
        (relationship["claim_identity"], relationship["claim_path"])
        for relationship in relationships
        if relationship["claim_identity"].startswith("claim:operation:")
        and relationship["claim_path"].startswith("/parameters/body/")
        and relationship["claim_path"].endswith("/required")
        and "." not in relationship["claim_path"].removeprefix(
            "/parameters/body/"
        ).removesuffix("/required")
        and relationship["relationship"] == "derived_support"
    }

    assert len(required_claims) == 86


def test_funkygames_ref_body_required_values_have_linked_derivations(
    tmp_path_factory,
) -> None:
    """One-hop ``items.$ref`` fields retain source-stated required flags."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-ref-body-required-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    required_claims = {
        (relationship["claim_identity"], relationship["claim_path"])
        for relationship in relationships
        if relationship["claim_identity"].startswith("claim:operation:")
        and relationship["claim_path"].startswith("/parameters/body/data[].")
        and relationship["claim_path"].endswith("/required")
        and relationship["relationship"] == "derived_support"
    }

    assert len(required_claims) == 9


def test_funkygames_documented_request_schemas_have_derivations(tmp_path_factory) -> None:
    """Every retained local request-body ref is re-derived by Core."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-request-schema-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    schema_claims = {
        relationship["claim_identity"]
        for relationship in relationships
        if relationship["claim_identity"].startswith("claim:operation:")
        and relationship["claim_path"] == "/request_schema_ref"
        and relationship["relationship"] == "derived_support"
    }

    assert len(schema_claims) == 25


def test_funkygames_request_schema_refs_have_verified_derivations(tmp_path_factory) -> None:
    """The 25 source-stated request schema refs reach Core via one mapping."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-request-schema-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    request_schema_claims = {
        relationship["claim_identity"]
        for relationship in relationships
        if relationship["claim_identity"].startswith("claim:operation:")
        and relationship["claim_path"] == "/request_schema_ref"
        and relationship["relationship"] == "derived_support"
    }

    assert len(request_schema_claims) == 25


def test_funkygames_request_body_field_names_have_derivations(tmp_path_factory) -> None:
    """Properties of each referenced request schema establish 95 body names."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-body-property-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    body_name_claims = {
        (relationship["claim_identity"], relationship["claim_path"])
        for relationship in relationships
        if relationship["claim_identity"].startswith("claim:operation:")
        and relationship["claim_path"].startswith("/parameters/body/")
        and relationship["claim_path"].endswith("/name")
        and relationship["relationship"] == "derived_support"
    }

    assert len(body_name_claims) == 95


def test_funkygames_direct_schema_claims_have_exact_derivations(
    tmp_path_factory,
) -> None:
    """The frozen Swagger directly proves 65 schema names and 258 fields."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-schema-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    direct_schema_derivations = {
        "openapi_schema_name_from_pointer",
        "openapi_schema_property_name_from_pointer",
        "openapi_schema_property_type_from_pointer",
        "openapi_schema_property_required_from_schema_pointer",
        "openapi_schema_name_from_pointer",
    }

    def derived_paths(path_predicate) -> set[tuple[str, str]]:
        return {
            (relationship["claim_identity"], relationship["claim_path"])
            for relationship in relationships
            if relationship["claim_identity"].startswith("claim:schema:")
            and relationship["relationship"] == "derived_support"
            and relationship["derivation_steps"][0]["name"]
            in direct_schema_derivations
            and path_predicate(relationship["claim_path"])
        }

    assert len(derived_paths(lambda path: path == "/name")) == 65
    assert len(
        derived_paths(
            lambda path: path.startswith("/fields/")
            and "." not in path
            and path.endswith("/name")
        )
    ) == 258
    assert len(
        derived_paths(
            lambda path: path.startswith("/fields/")
            and "." not in path
            and path.endswith("/type")
        )
    ) == 258
    assert len(
        derived_paths(
            lambda path: path.startswith("/fields/")
            and "." not in path
            and path.endswith("/required")
        )
    ) == 258


def test_funkygames_one_hop_schema_ref_fields_have_exact_derivations(
    tmp_path_factory,
) -> None:
    """One-hop component refs preserve all flattened schema field facts."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-ref-schema-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )

    def derived_paths(attribute: str) -> set[tuple[str, str]]:
        return {
            (relationship["claim_identity"], relationship["claim_path"])
            for relationship in relationships
            if relationship["claim_identity"].startswith("claim:schema:")
            and relationship["relationship"] == "derived_support"
            and relationship["claim_path"].startswith("/fields/")
            and "." in relationship["claim_path"]
            and relationship["claim_path"].endswith(attribute)
            and relationship["derivation_steps"][0]["name"].startswith(
                "openapi_schema_ref_property_"
            )
        }

    assert len(derived_paths("/name")) == 138
    assert len(derived_paths("/type")) == 138
    assert len(derived_paths("/required")) == 138


def test_funkygames_two_hop_schema_ref_fields_have_exact_derivations(
    tmp_path_factory,
) -> None:
    """The two explicitly bounded nested array chains remain source-grounded."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")
    result = run_assemble_pipeline(
        sources_root=case / "sources", extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-two-hop-schema-shadow"),
        run_id="bench-shadow", generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text("utf-8")
    )
    for attribute in ("name", "type", "required"):
        assert sum(
            relationship["relationship"] == "derived_support"
            and relationship["claim_path"].endswith(f"/{attribute}")
            and relationship["derivation_steps"][0]["name"]
            == f"openapi_schema_two_hop_ref_property_{attribute}_from_fragments"
            for relationship in relationships
        ) == 2


def test_funkygames_obeys_declared_core_parity_contract(tmp_path_factory) -> None:
    """The retained source snapshot satisfies its full Core graduation contract."""
    case = _case_by_name("funkygames-transfer-operator")
    if not _has_sources(case):
        pytest.skip("funkygames-transfer-operator: sources/ not present")

    expected = json.loads(
        (case / "expected" / "core-parity.json").read_text("utf-8")
    )
    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("funky-parity-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    run_dir = Path(result.run_dir)
    comparison = json.loads(
        (run_dir / "core" / "comparison.json").read_text("utf-8")
    )
    relationships = json.loads(
        (run_dir / "core" / "relationships.json").read_text("utf-8")
    )
    evidence = json.loads((run_dir / "core" / "evidence.json").read_text("utf-8"))
    precision_by_id = {
        fragment["id"]: fragment["precision"]
        for fragment in evidence["fragments"]
    }

    assert (
        comparison["legacy_status"]
        == expected["expected_legacy_status"].lower() + "ed"
    )
    assert comparison["core_verdict"] == expected["expected_core_verdict"]
    assert comparison["verdict_match"] is expected["require_verdict_match"]
    assert comparison["only_in_core"] == expected["allowed_semantic_differences"]
    assert expected["require_exact_evidence_for_all_material_claims"] is True
    assert comparison["claim_counts"]["unverified"] == 0
    assert all(
        relationship["relationship"] in {"explicit_support", "derived_support"}
        and precision_by_id[relationship["fragment_id"]] == "exact"
        and all(
            precision_by_id[fragment_id] == "exact"
            for fragment_id in relationship["context_fragment_ids"]
        )
        for relationship in relationships
    )


def test_rsg_obeys_declared_core_parity_contract(tmp_path_factory) -> None:
    """The structured RSG source snapshot satisfies its Core graduation contract."""
    case = _case_by_name("rsg-game-transfer-wallet")
    if not _has_sources(case):
        pytest.skip("rsg-game-transfer-wallet: sources/ not present")

    expected = json.loads(
        (case / "expected" / "core-parity.json").read_text("utf-8")
    )
    result = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        output_root=tmp_path_factory.mktemp("rsg-parity-shadow"),
        run_id="bench-shadow",
        generated_at=_FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    run_dir = Path(result.run_dir)
    comparison = json.loads(
        (run_dir / "core" / "comparison.json").read_text("utf-8")
    )
    relationships = json.loads(
        (run_dir / "core" / "relationships.json").read_text("utf-8")
    )
    evidence = json.loads((run_dir / "core" / "evidence.json").read_text("utf-8"))
    precision_by_id = {
        fragment["id"]: fragment["precision"]
        for fragment in evidence["fragments"]
    }

    assert (
        comparison["legacy_status"]
        == expected["expected_legacy_status"].lower() + "ed"
    )
    assert comparison["core_verdict"] == expected["expected_core_verdict"]
    assert comparison["verdict_match"] is expected["require_verdict_match"]
    assert comparison["only_in_core"] == expected["allowed_semantic_differences"]
    assert expected["require_exact_evidence_for_all_material_claims"] is True
    assert comparison["claim_counts"]["unverified"] == 0
    assert all(
        relationship["relationship"] in {"explicit_support", "derived_support"}
        and precision_by_id[relationship["fragment_id"]] == "exact"
        and all(
            precision_by_id[fragment_id] == "exact"
            for fragment_id in relationship["context_fragment_ids"]
        )
        for relationship in relationships
    )


def test_benchmark_diff_identity(case, assembled, tmp_path) -> None:
    """Diffing a run against a byte-identical copy of itself yields no semantic
    change. `source_only` differences (provenance/manifest source paths) are
    allowed and never asserted on; the breaking/additive/changed sets must be
    empty. This is the spurious-diff regression net."""
    run_dir = Path(assembled.run_dir)
    copy = tmp_path / "identical" / run_dir.name
    shutil.copytree(run_dir, copy)

    report = build_diff_report(load_run_artifacts(run_dir), load_run_artifacts(copy))
    semantic = [
        f for f in report.findings
        if f.impact in {DiffImpact.BREAKING, DiffImpact.ADDITIVE, DiffImpact.CHANGED}
    ]
    assert not semantic, (
        f"{case.name}: self-diff produced spurious semantic findings — "
        f"{[(f.impact.value, f.location, f.summary) for f in semantic]}"
    )


def _mutate_stripe_extraction(src: Path, dst: Path) -> None:
    """Copytree the stripe extraction dir `src` into `dst`, then apply three
    known mutations that each produce exactly one diff finding:
      (breaking) remove the /capture endpoint (ep5.json + inventory entry),
      (additive) add a new increment_authorization endpoint (ep6.json + entry),
      (changed)  flip PaymentIntent.description from required:true to false.
    Proven against real stripe data before this plan was written."""
    shutil.copytree(src, dst)
    inv = json.loads((dst / "inventory.json").read_text("utf-8"))

    # (breaking) remove the capture endpoint
    inv["endpoints"] = [e for e in inv["endpoints"] if not e["path"].endswith("/capture")]
    (dst / "endpoints" / "ep5.json").unlink()

    # (additive) add a brand-new endpoint (inventory summary + full detail file)
    inv["endpoints"].append({
        "method": "POST",
        "path": "/v1/payment_intents/{intent}/increment_authorization",
        "summary": "Increment an authorization",
        "source": "paths./v1/payment_intents/{intent}/increment_authorization.post",
    })
    ep6 = {
        "method": "POST",
        "path": "/v1/payment_intents/{intent}/increment_authorization",
        "source": "paths./v1/payment_intents/{intent}/increment_authorization.post",
        "parameters": [
            {"name": "amount", "in": "body", "type": "integer", "required": True,
             "description": "New total amount to authorize."},
        ],
        "request": {"content_type": "application/x-www-form-urlencoded",
                    "schema": None, "required": True, "description": "Form body."},
        "responses": [{"status": "200", "description": "Returns the PaymentIntent object.",
                       "schema": None, "schema_ref": "PaymentIntent"}],
        "tags": ["Payment Intents"],
        "security": ["bearerAuth"],
        "examples": [],
        "missing": [],
    }
    (dst / "endpoints" / "ep6.json").write_text(json.dumps(ep6, indent=2), encoding="utf-8")

    # (changed) loosen one required schema field to optional
    for field in inv["schemas"][0]["fields"]:
        if field["name"] == "description":
            field["required"] = False
    (dst / "inventory.json").write_text(json.dumps(inv, indent=2), encoding="utf-8")


def test_benchmark_diff_detects_change(tmp_path_factory, tmp_path) -> None:
    """stripe baseline vs a v2 built from three known extraction mutations must
    surface one breaking, one additive, and one changed finding, each anchored to
    the mutated operation/field. If the mutated extraction fails to assemble, that
    is a real finding (mutation helper wrong, or assemble regressed) — investigate,
    do not weaken."""
    case = _case_by_name(_STRIPE)
    baseline = _assemble_case(case, tmp_path_factory)  # skips if sources absent

    mutated_ext = tmp_path / "extraction2"
    _mutate_stripe_extraction(case / "extraction", mutated_ext)
    v2 = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=mutated_ext,
        output_root=tmp_path / "v2_out",
        run_id="v2",
        generated_at=_FIXED_TS,
    )

    report = build_diff_report(
        load_run_artifacts(Path(baseline.run_dir)),
        load_run_artifacts(Path(v2.run_dir)),
    )
    by_impact: dict[DiffImpact, list] = {i: [] for i in DiffImpact}
    for finding in report.findings:
        by_impact[finding.impact].append(finding)

    assert any(
        "capture" in f.location and f.summary == "operation removed"
        for f in by_impact[DiffImpact.BREAKING]
    ), f"missing breaking (capture removed): {[(f.location, f.summary) for f in by_impact[DiffImpact.BREAKING]]}"
    assert any(
        "increment_authorization" in f.location and f.summary == "operation added"
        for f in by_impact[DiffImpact.ADDITIVE]
    ), f"missing additive (increment added): {[(f.location, f.summary) for f in by_impact[DiffImpact.ADDITIVE]]}"
    assert any(
        f.location == "components.schemas.PaymentIntent.description"
        and f.summary == "property no longer required"
        for f in by_impact[DiffImpact.CHANGED]
    ), f"missing changed (description loosened): {[(f.location, f.summary) for f in by_impact[DiffImpact.CHANGED]]}"


def _score_candidate(run_dir: Path) -> int:
    """Compute the CI-profile score for a run dir, write it to <run_dir>/score/
    (the path approve_candidate reads via _read_score), and return the score.
    The assembled run dir has no score.json, so the min_score gate needs this."""
    report = evaluate_score(load_score_inputs(run_dir), profile=ScoreProfile.CI)
    write_score_reports(report, run_dir / "score")
    return report.score


def test_benchmark_foundry_supersession(tmp_path_factory, tmp_path) -> None:
    """A second asset records supersession without rewriting the first and moves
    the `current` pointer. Two distinct timestamps are required because
    make_asset_id is one-second-resolution; identical timestamps would collide."""
    case = _case_by_name(_STRIPE)
    run = _assemble_case(case, tmp_path_factory)  # skips if sources absent
    run_dir = Path(run.run_dir)

    v1_dir = tmp_path / "runs" / "v1"
    v2_dir = tmp_path / "runs" / "v2"
    shutil.copytree(run_dir, v1_dir)
    shutil.copytree(run_dir, v2_dir)

    root = tmp_path / "project"  # fresh .foundry/, zero pollution
    root.mkdir()
    register_docset(root, Docset(
        docset_id="bench", title=case.name, provider="bench", product="bench",
    ))
    import_run(root, "bench", v1_dir)  # run_id == "v1" (run_dir.name)
    import_run(root, "bench", v2_dir)  # run_id == "v2"

    asset_v1 = approve_candidate(root, "bench", "v1", approved_by="bench", now=_FIXED_TS)
    asset_v2 = approve_candidate(
        root, "bench", "v2", approved_by="bench", now=_FIXED_TS + timedelta(seconds=1),
    )

    prior = foundry_store.load_asset(root, "bench", asset_v1.asset_id)
    assert prior.status is AssetStatus.APPROVED, (
        f"v1 immutable approval status changed to {prior.status.value}"
    )
    assert asset_v2.supersedes == asset_v1.asset_id
    current = load_current_asset(root, "bench")
    assert current.asset_id == asset_v2.asset_id, "current pointer should resolve to v2"


def test_benchmark_foundry_min_score_gate(tmp_path_factory, tmp_path) -> None:
    """approve_candidate rejects a candidate whose score is below min_score and
    accepts one that meets it. allow_failing does NOT bypass this gate (it only
    bypasses the validation-ok gate), so the success path uses a met min_score.
    The candidate needs a real score.json (the run dir has none) — see
    _score_candidate."""
    case = _case_by_name(_STRIPE)
    run = _assemble_case(case, tmp_path_factory)  # skips if sources absent

    cand_dir = tmp_path / "runs" / "gate"
    shutil.copytree(Path(run.run_dir), cand_dir)
    score = _score_candidate(cand_dir)  # writes cand_dir/score/score.json

    root = tmp_path / "project"
    root.mkdir()
    register_docset(root, Docset(
        docset_id="bench", title=case.name, provider="bench", product="bench",
    ))
    import_run(root, "bench", cand_dir)  # run_id == "gate"

    with pytest.raises(FoundryApprovalError):
        approve_candidate(
            root, "bench", "gate", approved_by="bench", now=_FIXED_TS,
            min_score=score + 1,
        )

    asset = approve_candidate(
        root, "bench", "gate", approved_by="bench", now=_FIXED_TS, min_score=score,
    )
    current = load_current_asset(root, "bench")
    assert current.asset_id == asset.asset_id, "met-min_score approval should become current"


def test_benchmark_preparation(case, assembled) -> None:
    """preparation-report.json parses to a PreparationReport with a valid status,
    a non-empty phases list, and only error/warning finding severities. Invariant:
    a validation-PASS case cannot have been preparation-blocked. EXPECTED_FAIL
    cases (e.g. paypal) may hold any status."""
    run_dir = Path(assembled.run_dir)
    report = PreparationReport.model_validate_json(
        (run_dir / "preparation-report.json").read_text("utf-8")
    )

    assert report.status in set(PreparationStatus), f"{case.name}: invalid preparation status"
    assert report.phases, f"{case.name}: preparation phases empty"
    for phase in report.phases:
        for finding in phase.findings:
            assert finding.severity in {PreparationSeverity.ERROR, PreparationSeverity.WARNING}, (
                f"{case.name}: unexpected preparation severity {finding.severity!r}"
            )

    expect = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))
    if expect.get("current_status") == "PASS":
        assert report.status is not PreparationStatus.BLOCKED, (
            f"{case.name}: validation-PASS case must not be preparation-blocked"
        )


def test_benchmark_score_verdict(case, assembled) -> None:
    """From the real ScoreReport: (a) classify_findings is a lossless, disjoint
    partition; (b) loop_verdict returns a valid LoopVerdict, deterministic across
    a second identical call; (c) coupling invariant — score >= min_score implies
    CONVERGED (the loop must not ask for more correction once the target is met)."""
    run_dir = Path(assembled.run_dir)
    report = evaluate_score(load_score_inputs(run_dir), profile=ScoreProfile.CI)

    # (a) lossless, disjoint partition
    reducible, irreducible = classify_findings(report.findings)
    assert len(reducible) + len(irreducible) == len(report.findings), (
        f"{case.name}: classify_findings dropped or duplicated findings"
    )
    for finding in report.findings:
        assert (finding in reducible) ^ (finding in irreducible), (
            f"{case.name}: finding not in exactly one partition: {finding.code}"
        )

    # (b) valid + deterministic verdict
    kwargs = dict(
        prev_score=None, curr_score=report.score, target=report.min_score,
        round_index=1, max_rounds=3, findings=report.findings,
    )
    first = loop_verdict(**kwargs)
    again = loop_verdict(**kwargs)
    assert first.verdict in set(LoopVerdict), f"{case.name}: invalid loop verdict"
    assert first.verdict == again.verdict, f"{case.name}: loop verdict not deterministic"

    # (c) coupling invariant
    if report.score >= report.min_score:
        assert first.verdict is LoopVerdict.CONVERGED, (
            f"{case.name}: score {report.score} >= min {report.min_score} but verdict "
            f"is {first.verdict.value}, not converged"
        )


def test_benchmark_extraction_passes_the_gate(case) -> None:
    """每個 benchmark case 的 extraction/ 都必須通過 check_extraction。

    這是擋下「過緊的不變式」的回歸網:設計期間 index-strict 對應就是被這條
    測試否決的(apis-guru-baseline 的 ep3/ep4/ep5 順序本來就不對位)。
    """
    if not _has_sources(case):
        pytest.skip(f"{case.name}: sources/ not present (operator-provided, gitignored)")

    violations = verify_extraction_dir(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        generated_at=_FIXED_TS,
    )

    assert violations == [], f"{case.name}: {violations}"


@pytest.mark.parametrize("case_id", required_sanitized_benchmark_cases())
def test_sanitized_fixture_is_a_true_redaction_of_the_original_snapshot(
    case_id: str,
) -> None:
    """A sanitized subset must be derived from the real snapshot, not authored.

    `tests/test_sanitized_benchmarks.py` can only check the subset against itself:
    the original is gitignored, so CI cannot tell a redaction from synthetic
    content. That distinction is the whole premise of the lane, so it is asserted
    here in the source-backed layer, where `--strict-local` forbids a skip.
    """
    case = _case_by_name(case_id)
    descriptor_path = case / "sanitized-fixture.json"
    assert descriptor_path.is_file(), f"{case_id}: sanitized-fixture.json is missing"
    if not _has_sources(case):
        pytest.skip(f"{case.name}: sources/ not present (operator-provided, gitignored)")

    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    original_path = case / descriptor["original_snapshot"]["path"]
    assert original_path.is_file(), f"{case.name}: {original_path} is missing"
    assert (
        hashlib.sha256(original_path.read_bytes()).hexdigest()
        == descriptor["original_snapshot"]["sha256"]
    ), f"{case.name}: original snapshot does not match the recorded digest"

    original = original_path.read_text(encoding="utf-8").splitlines()
    sanitized = (
        (case / descriptor["sanitized_source"]["path"])
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(sanitized) == len(original), (
        f"{case.name}: sanitized subset must preserve the original line coordinates"
    )
    retained = {
        line_number
        for start, end in descriptor["sanitization"]["retained_line_ranges"]
        for line_number in range(start, end + 1)
    }
    for number, (kept, source_line) in enumerate(zip(sanitized, original), start=1):
        if not kept:
            continue
        assert number in retained, (
            f"{case.name}: line {number} is not inside a declared retained range"
        )
        assert kept == source_line, (
            f"{case.name}: line {number} does not match the original snapshot"
        )
    blanked = [
        number
        for number in sorted(retained)
        if number <= len(sanitized)
        and not sanitized[number - 1]
        and original[number - 1]
    ]
    assert blanked == [], (
        f"{case.name}: declared-retained lines were dropped: {blanked[:5]}"
    )


def _descriptor_relative_path(case_id: str, key: str, relative: str) -> Path:
    """Reject a descriptor-declared path that would escape the case directory
    (absolute, or containing `..`) before it is ever joined."""
    candidate = Path(relative)
    assert not candidate.is_absolute() and ".." not in candidate.parts, (
        f"{case_id}: {key}.path must be a case-relative path with no '..'"
    )
    return candidate


@pytest.mark.parametrize("case_id", required_source_derivation_benchmark_cases())
def test_local_markdown_matches_recorded_source_derivation(
    case_id: str, tmp_path: Path
) -> None:
    """`source-derivation.json` is the only *tracked* anchor for a PDF case's
    Markdown — both `raw/` and `sources/` are gitignored (ADR 0013), so neither
    the original PDF nor its Markdown is ever "committed" in this repo's sense.

    The local Markdown's digest is checked unconditionally wherever that file
    exists (one hash, no reason to gate it on `raw/` too); re-deriving it from
    the original PDF additionally needs the gitignored `raw/` copy, so only
    that half SKIPs like every other source-backed assertion when it is
    absent.
    """
    case = _case_by_name(case_id)
    descriptor_path = case / "source-derivation.json"
    assert descriptor_path.is_file(), f"{case_id}: source-derivation.json is missing"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    assert descriptor["case_id"] == case_id, (
        f"{case_id}: source-derivation.json case_id does not match its directory"
    )
    assert descriptor["conversion_tool"] == "pymupdf4llm", (
        f"{case_id}: this test only exercises pymupdf4llm; a different declared "
        "conversion tool needs its own re-derivation assertion"
    )

    local_markdown_path = case / _descriptor_relative_path(
        case_id, "derived_markdown", descriptor["derived_markdown"]["path"]
    )
    original_path = case / _descriptor_relative_path(
        case_id, "original_document", descriptor["original_document"]["path"]
    )

    if local_markdown_path.is_file():
        assert (
            hashlib.sha256(local_markdown_path.read_bytes()).hexdigest()
            == descriptor["derived_markdown"]["sha256"]
        ), f"{case.name}: local markdown does not match the recorded digest"
    elif not original_path.is_file():
        pytest.skip(
            f"{case.name}: neither {local_markdown_path} nor {original_path} "
            "present (operator-provided, gitignored)"
        )

    if not original_path.is_file():
        pytest.skip(
            f"{case.name}: {original_path} not present (operator-provided, "
            "gitignored); local markdown digest already verified above"
        )

    assert (
        hashlib.sha256(original_path.read_bytes()).hexdigest()
        == descriptor["original_document"]["sha256"]
    ), f"{case.name}: original PDF does not match the recorded digest"

    result = prepare_markdown(original_path, tmp_path)
    assert len(result.converted) == 1, f"{case.name}: expected exactly one converted file"
    derived_markdown_path = tmp_path / result.converted[0]

    assert (
        hashlib.sha256(derived_markdown_path.read_bytes()).hexdigest()
        == descriptor["derived_markdown"]["sha256"]
    ), f"{case.name}: re-converted markdown does not match the recorded digest"

    if local_markdown_path.is_file():
        assert derived_markdown_path.read_bytes() == local_markdown_path.read_bytes(), (
            f"{case.name}: re-converting the original PDF no longer reproduces "
            "the local markdown byte-for-byte; a pymupdf4llm upgrade likely "
            "changed conversion output — re-derive this case's evidence and "
            "record what moved"
        )
