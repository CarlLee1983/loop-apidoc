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
import shutil
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from openapi_spec_validator import validate as validate_openapi

from loop_apidoc.agentcli.assemble import run_assemble_pipeline
from loop_apidoc.diff import DiffImpact, build_diff_report, load_run_artifacts
from loop_apidoc.foundry import store as foundry_store
from loop_apidoc.foundry.approve import approve_candidate
from loop_apidoc.foundry.importer import import_run
from loop_apidoc.foundry.models import AssetStatus, Docset, FoundryApprovalError
from loop_apidoc.foundry.query import load_current_asset, resolve_current_artifact
from loop_apidoc.foundry.register import register_docset
from loop_apidoc.run.models import RunResult
from loop_apidoc.score import ScoreProfile, evaluate_score, load_score_inputs, write_reports as write_score_reports

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


_STRIPE = "stripe-basic-rest"


def _case_by_name(name: str) -> Path:
    return _BENCH_ROOT / name


def _assemble_case(case: Path, tmp_path_factory) -> RunResult:
    """Assemble a case at most once per session and memoize the RunResult.

    Skips when the case's operator-provided sources are absent. The produced run
    dir is treated read-only by every consumer (score reads it; foundry/diff
    copytree FROM it), so a single shared dir is safe. Non-parametrized tests
    reuse this same helper via `_case_by_name` so they never re-assemble."""
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
            "ecpay-creditcard-pdf", "adyen-payments-multimethod"} <= names


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
    """Approving a second asset for the same docset supersedes the first and
    moves the `current` pointer. Two distinct timestamps are required because
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

    superseded = foundry_store.load_asset(root, "bench", asset_v1.asset_id)
    assert superseded.status is AssetStatus.SUPERSEDED, (
        f"v1 asset should be superseded, got {superseded.status.value}"
    )
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
