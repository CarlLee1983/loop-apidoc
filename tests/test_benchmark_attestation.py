"""Behavioral contract for the per-case benchmark attestation.

The seam under test is `scripts/benchmark_attestation.py` as a repository-level
command: its report document, its Markdown rendering, and its refusals. The
harness run itself is injected as `HarnessOutcome`s rather than executed, so these
tests assert what the attestation *concludes* from a result and never re-run the
benchmark suite inside it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts import benchmark_attestation as attestation
from scripts import quality_gate
from scripts.benchmark_attestation import AttestationError, Binding, HarnessOutcome


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = REPO_ROOT / "benchmarks"
SANITIZED_CASE = "rsg-game-transfer-wallet"
DERIVATION_CASE = "ecpay-creditcard-pdf"
EXPECTED_FAIL_CASE = "paypal-webhooks-incomplete"
PLAIN_CASE = "newebpay-mpg"

CREDENTIAL_URL = (
    "https://example.test/spec.pdf?X-Amz-Signature=6f1c2a9b4d8e0f3a5c7b9d1e2f4a6c8b"
)
JWT_PAYLOAD = (
    "AssertionError: token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0."
    "7Hk3QpX9sVfLm2Nq0RtYwZbCdEfGhIjKlMnOpQrStUv"
)
SUPPLIER_SECRET = "MerchantSecretKey=8f4c1b0a9d6e3f27"

BINDING = Binding(
    repository_commit="0" * 40,
    repository_dirty=False,
    loop_apidoc_version="0.0.0",
)


def _committed_root(tmp_path: Path) -> Path:
    """A writable copy of the committed benchmark tree.

    Only committed files are copied: the operator-provided `sources/`,
    `source-quality/` and `raw/` trees are gitignored and absent on CI, which is
    precisely the condition most of these tests need to reproduce.
    """
    root = tmp_path / "benchmarks"
    shutil.copytree(BENCHMARKS, root)
    for case in root.iterdir():
        for operator_tree in ("sources", "source-quality", "raw", "work", "output"):
            shutil.rmtree(case / operator_tree, ignore_errors=True)
    return root


def _build(root: Path, *, mode: str = "ci-safe", outcomes=()) -> dict:
    return attestation.build_attestation(
        benchmark_root=root, mode=mode, binding=BINDING, outcomes=outcomes
    )


def _case(report: dict, case_id: str) -> dict:
    return next(case for case in report["cases"] if case["case_id"] == case_id)


def _edit_json(path: Path, **changes) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    document.update(changes)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


# --- inventory (AC-002, AC-003) --------------------------------------------


def test_every_required_case_appears_exactly_once(tmp_path: Path) -> None:
    report = _build(_committed_root(tmp_path))

    reported = [case["case_id"] for case in report["cases"]]

    assert sorted(reported) == sorted(quality_gate.REQUIRED_BENCHMARK_CASES)
    assert len(reported) == len(set(reported))


def test_inventory_tracks_the_reviewed_required_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing a case from the reviewed inventory removes it from the report.

    There is no second list to update: the attestation reads
    `REQUIRED_BENCHMARK_CASES` and refuses any committed fixture the inventory
    does not name.
    """
    root = _committed_root(tmp_path)
    reduced = tuple(
        case for case in quality_gate.REQUIRED_BENCHMARK_CASES if case != PLAIN_CASE
    )
    monkeypatch.setattr(quality_gate, "REQUIRED_BENCHMARK_CASES", reduced)

    with pytest.raises(AttestationError, match=PLAIN_CASE):
        _build(root)

    shutil.rmtree(root / PLAIN_CASE)
    report = _build(root)

    assert [case["case_id"] for case in report["cases"]] == sorted(reduced)


# --- assurance levels (AC-004..AC-007) -------------------------------------


def test_missing_source_prerequisites_are_named_and_never_source_backed(
    tmp_path: Path,
) -> None:
    report = _build(_committed_root(tmp_path))
    case = _case(report, PLAIN_CASE)

    assert case["unavailable_prerequisites"] == ["source-quality/", "sources/"]
    assert case["assurance"]["prerequisites_available"] is False
    assert case["assurance"]["source_backed_executed"] is False
    assert case["assurance"]["strict_local_passed"] is False
    assert "prerequisites-unavailable" in case["reasons"]
    assert "source-backed-execution-not-established" in case["reasons"]


def test_a_skip_is_never_reported_as_a_pass(tmp_path: Path) -> None:
    outcomes = (
        HarnessOutcome(
            module=attestation.BENCHMARK_TEST_MODULE,
            test=attestation.SOURCE_BACKED_PRIMARY_TEST,
            case_id=PLAIN_CASE,
            outcome="skipped",
            message="sources/ not present",
        ),
    )

    case = _case(_build(_committed_root(tmp_path), outcomes=outcomes), PLAIN_CASE)

    assert case["assurance"]["source_backed_executed"] is False
    assert case["harness"]["conformant"] is None
    assert case["harness"]["skipped"] == 1
    assert case["contract_validation"]["observed_status"] is None
    assert "source-backed-assertions-skipped" in case["reasons"]


def test_sanitized_replay_is_separated_from_source_backed_assurance(
    tmp_path: Path,
) -> None:
    outcomes = (
        HarnessOutcome(
            module=attestation.SANITIZED_TEST_MODULE,
            test=attestation.SANITIZED_EXACT_EVIDENCE_TEST,
            case_id=SANITIZED_CASE,
            outcome="passed",
            message="",
        ),
    )

    case = _case(_build(_committed_root(tmp_path), outcomes=outcomes), SANITIZED_CASE)

    assert case["assurance"]["sanitized_fixture_executed"] is True
    assert case["assurance"]["exact_evidence_parity"] == "sanitized_fixture_replay"
    assert case["assurance"]["source_backed_executed"] is False
    assert case["assurance"]["strict_local_passed"] is False
    assert "sanitized-fixture-replay-passed" in case["reasons"]


def test_exact_evidence_parity_needs_an_actual_replay(tmp_path: Path) -> None:
    """The lane declaration is not the evidence (R8).

    Every committed case declares `require_exact_evidence_for_all_material_claims`
    and both lane members are named in the reviewed inventory; neither fact makes
    the replay have happened.
    """
    report = _build(_committed_root(tmp_path))

    for case_id in quality_gate.required_exact_evidence_parity_benchmark_cases():
        case = _case(report, case_id)
        assert case["lanes"]["exact_evidence_parity"] is True
        assert case["assurance"]["exact_evidence_parity"] == "not_established"
        assert "exact-evidence-parity-not-replayed" in case["reasons"]

    replayed = _case(
        _build(
            _committed_root(tmp_path / "second"),
            outcomes=(
                HarnessOutcome(
                    module=attestation.BENCHMARK_TEST_MODULE,
                    test=attestation.EXACT_EVIDENCE_PARITY_TEST,
                    case_id=SANITIZED_CASE,
                    outcome="passed",
                    message="",
                ),
            ),
        ),
        SANITIZED_CASE,
    )
    assert replayed["assurance"]["exact_evidence_parity"] == "source_backed_replay"


def test_expected_fail_case_keeps_a_failing_contract_status_while_conformant(
    tmp_path: Path,
) -> None:
    outcomes = (
        HarnessOutcome(
            module=attestation.BENCHMARK_TEST_MODULE,
            test=attestation.SOURCE_BACKED_PRIMARY_TEST,
            case_id=EXPECTED_FAIL_CASE,
            outcome="passed",
            message="",
        ),
    )

    case = _case(_build(_committed_root(tmp_path), outcomes=outcomes), EXPECTED_FAIL_CASE)

    assert case["harness"]["expectation"] == "EXPECTED_FAIL"
    assert case["harness"]["conformant"] is True
    assert case["contract_validation"]["declared_status"] == "FAIL"
    assert case["contract_validation"]["harness_classification"] == "EXPECTED_FAIL"
    assert case["contract_validation"]["observed_status"] == "FAIL"


def test_harness_conformance_separates_not_established_from_contradicted(
    tmp_path: Path,
) -> None:
    """`false` must mean the harness contradicted its expectation.

    A case whose source-backed assertions never ran has established nothing
    either way; reporting that as a conformance failure invents a violation, and
    reporting it as conformance invents a pass.
    """
    root = _committed_root(tmp_path)

    not_established = _case(_build(root), PLAIN_CASE)["harness"]["conformant"]
    contradicted = _case(
        _build(
            root,
            outcomes=(
                HarnessOutcome(
                    module=attestation.BENCHMARK_TEST_MODULE,
                    test=attestation.SOURCE_BACKED_PRIMARY_TEST,
                    case_id=PLAIN_CASE,
                    outcome="failed",
                    message="issue-class map drift",
                ),
            ),
        ),
        PLAIN_CASE,
    )["harness"]["conformant"]

    assert not_established is None
    assert contradicted is False


def test_strict_local_passed_requires_prerequisites_and_a_clean_execution(
    tmp_path: Path,
) -> None:
    root = _committed_root(tmp_path)
    for case_id in quality_gate.REQUIRED_BENCHMARK_CASES:
        _stock_operator_assets(root / case_id)
    outcomes = tuple(
        HarnessOutcome(
            module=attestation.BENCHMARK_TEST_MODULE,
            test=attestation.SOURCE_BACKED_PRIMARY_TEST,
            case_id=case_id,
            outcome="passed",
            message="",
        )
        for case_id in quality_gate.REQUIRED_BENCHMARK_CASES
    )

    strict = _build(root, mode="strict-local", outcomes=outcomes)
    ci_safe = _build(root, mode="ci-safe", outcomes=outcomes)

    assert _case(strict, PLAIN_CASE)["assurance"]["strict_local_passed"] is True
    assert _case(ci_safe, PLAIN_CASE)["assurance"]["strict_local_passed"] is False
    assert _case(ci_safe, PLAIN_CASE)["assurance"]["strict_local_eligible"] is True


def _stock_operator_assets(case_dir: Path, *, source_text: str = "# spec\n") -> None:
    (case_dir / "sources").mkdir(parents=True, exist_ok=True)
    (case_dir / "sources" / "spec.md").write_text(source_text, encoding="utf-8")
    quality = case_dir / "source-quality"
    quality.mkdir(parents=True, exist_ok=True)
    for name in quality_gate.BENCHMARK_QUALITY_FILES:
        (quality / name).write_text("{}", encoding="utf-8")
    descriptor = case_dir / attestation.SOURCE_DERIVATION_DESCRIPTOR
    if descriptor.is_file():
        declared = json.loads(descriptor.read_text(encoding="utf-8"))
        original = case_dir / declared["original_document"]["path"]
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(b"%PDF-1.4\n")


# --- fail closed (AC-008) --------------------------------------------------


def _corrupt_unreadable_expectation(root: Path) -> None:
    (root / PLAIN_CASE / "expected" / "validation.expect.json").write_text(
        "{not json", encoding="utf-8"
    )


def _corrupt_unusable_status(root: Path) -> None:
    _edit_json(
        root / PLAIN_CASE / "expected" / "validation.expect.json",
        current_status="PROBABLY",
    )


def _corrupt_parity_version(root: Path) -> None:
    _edit_json(root / PLAIN_CASE / "expected" / "core-parity.json", schema_version=2)


def _corrupt_contradictory_parity(root: Path) -> None:
    _edit_json(
        root / PLAIN_CASE / "expected" / "core-parity.json",
        expected_legacy_status="FAIL",
    )


def _corrupt_missing_parity(root: Path) -> None:
    (root / PLAIN_CASE / "expected" / "core-parity.json").unlink()


def _corrupt_tampered_sanitized_source(root: Path) -> None:
    descriptor = json.loads(
        (root / SANITIZED_CASE / attestation.SANITIZED_DESCRIPTOR).read_text("utf-8")
    )
    source = root / SANITIZED_CASE / descriptor["sanitized_source"]["path"]
    source.write_text(source.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")


def _corrupt_sanitized_case_identity(root: Path) -> None:
    _edit_json(
        root / SANITIZED_CASE / attestation.SANITIZED_DESCRIPTOR,
        case_id="some-other-case",
    )


def _corrupt_sanitized_strict_local_claim(root: Path) -> None:
    _edit_json(
        root / SANITIZED_CASE / attestation.SANITIZED_DESCRIPTOR,
        strict_local_eligible=True,
    )


def _corrupt_stale_derived_markdown(root: Path) -> None:
    descriptor = json.loads(
        (root / DERIVATION_CASE / attestation.SOURCE_DERIVATION_DESCRIPTOR).read_text("utf-8")
    )
    derived = root / DERIVATION_CASE / descriptor["derived_markdown"]["path"]
    derived.parent.mkdir(parents=True, exist_ok=True)
    derived.write_text("a newer document\n", encoding="utf-8")


def _corrupt_escaping_derivation_path(root: Path) -> None:
    path = root / DERIVATION_CASE / attestation.SOURCE_DERIVATION_DESCRIPTOR
    descriptor = json.loads(path.read_text(encoding="utf-8"))
    descriptor["derived_markdown"]["path"] = "../../etc/passwd"
    path.write_text(json.dumps(descriptor, indent=2), encoding="utf-8")


@pytest.mark.parametrize(
    "corrupt",
    [
        _corrupt_unreadable_expectation,
        _corrupt_unusable_status,
        _corrupt_parity_version,
        _corrupt_contradictory_parity,
        _corrupt_missing_parity,
        _corrupt_tampered_sanitized_source,
        _corrupt_sanitized_case_identity,
        _corrupt_sanitized_strict_local_claim,
        _corrupt_stale_derived_markdown,
        _corrupt_escaping_derivation_path,
    ],
    ids=lambda function: function.__name__.removeprefix("_corrupt_"),
)
def test_malformed_stale_or_tampered_input_fails_closed(corrupt, tmp_path: Path) -> None:
    root = _committed_root(tmp_path)
    corrupt(root)

    with pytest.raises(AttestationError):
        _build(root)


def test_strict_local_mode_refuses_an_unavailable_prerequisite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _committed_root(tmp_path)
    monkeypatch.setattr(attestation, "run_harness", lambda *, root: ((), 0))
    monkeypatch.setattr(attestation, "repository_binding", lambda *, root: BINDING)

    exit_code = attestation.main(
        [
            "--mode",
            "strict-local",
            "--benchmark-root",
            str(root),
            "--json-out",
            str(tmp_path / "report.json"),
        ]
    )

    assert exit_code == 1
    assert not (tmp_path / "report.json").exists()


# --- schema, determinism and binding (AC-009, AC-011, AC-012) ---------------


def test_schema_is_strict_about_unknown_fields(tmp_path: Path) -> None:
    report = _build(_committed_root(tmp_path))
    attestation.validate_report(report)

    report["cases"][0]["confidence"] = "high"

    with pytest.raises(AttestationError, match="benchmark-attestation/v1"):
        attestation.validate_report(report)


def test_report_ordering_is_deterministic(tmp_path: Path) -> None:
    first = _build(_committed_root(tmp_path))
    second = _build(_committed_root(tmp_path / "again"))

    assert first == second
    assert [case["case_id"] for case in first["cases"]] == sorted(
        quality_gate.REQUIRED_BENCHMARK_CASES
    )
    for case in first["cases"]:
        assert case["reasons"] == sorted(case["reasons"])
        assert case["unavailable_prerequisites"] == sorted(
            case["unavailable_prerequisites"]
        )


def test_report_binds_revision_version_mode_and_contract_versions(
    tmp_path: Path,
) -> None:
    report = _build(_committed_root(tmp_path), mode="strict-local")

    assert report["schema_version"] == "benchmark-attestation/v1"
    assert report["binding"]["repository_commit"] == "0" * 40
    assert report["binding"]["loop_apidoc_version"] == "0.0.0"
    assert report["binding"]["execution_mode"] == "strict-local"
    assert report["binding"]["contract_versions"] == {
        "core_parity": 1,
        "sanitized_fixture": 1,
        "source_derivation": 1,
    }


def test_unknown_execution_mode_is_refused(tmp_path: Path) -> None:
    with pytest.raises(AttestationError, match="unknown execution mode"):
        _build(_committed_root(tmp_path), mode="nearly-strict")


# --- rendering agreement (AC-010) ------------------------------------------


def test_markdown_states_the_same_status_and_reasons_as_the_json(
    tmp_path: Path,
) -> None:
    outcomes = (
        HarnessOutcome(
            module=attestation.BENCHMARK_TEST_MODULE,
            test=attestation.SOURCE_BACKED_PRIMARY_TEST,
            case_id=EXPECTED_FAIL_CASE,
            outcome="passed",
            message="",
        ),
        HarnessOutcome(
            module=attestation.SANITIZED_TEST_MODULE,
            test=attestation.SANITIZED_EXACT_EVIDENCE_TEST,
            case_id=SANITIZED_CASE,
            outcome="passed",
            message="",
        ),
    )
    report = _build(_committed_root(tmp_path), outcomes=outcomes)

    markdown = attestation.render_markdown(report)

    for case in report["cases"]:
        row = next(
            line
            for line in markdown.splitlines()
            if line.startswith(f"| `{case['case_id']}` |")
        )
        assert case["harness"]["expectation"] in row
        assert case["contract_validation"]["declared_status"] in row
        assert case["assurance"]["exact_evidence_parity"] in row
        reason_line = next(
            line
            for line in markdown.splitlines()
            if line.startswith(f"* `{case['case_id']}`: ")
        )
        for reason in case["reasons"]:
            assert f"`{reason}`" in reason_line


# --- security fixture matrix (AC-013, AC-014) ------------------------------


def test_credential_bearing_source_url_is_redacted_in_both_outputs(
    tmp_path: Path,
) -> None:
    root = _committed_root(tmp_path)
    path = root / SANITIZED_CASE / attestation.SANITIZED_DESCRIPTOR
    descriptor = json.loads(path.read_text(encoding="utf-8"))
    descriptor["original_snapshot"]["source_url"] = CREDENTIAL_URL
    path.write_text(json.dumps(descriptor, indent=2), encoding="utf-8")

    report = _build(root)
    markdown = attestation.render_markdown(report)
    rendered = json.dumps(report, ensure_ascii=False)

    url = _case(report, SANITIZED_CASE)["source_reference"]["url"]
    assert url == "https://example.test/spec.pdf?X-Amz-Signature=[REDACTED]"
    assert "6f1c2a9b4d8e0f3a5c7b9d1e2f4a6c8b" not in rendered
    assert "6f1c2a9b4d8e0f3a5c7b9d1e2f4a6c8b" not in markdown
    assert url in markdown


def test_report_never_persists_an_absolute_path(tmp_path: Path) -> None:
    root = _committed_root(tmp_path)
    _stock_operator_assets(root / PLAIN_CASE)

    report = _build(root)
    rendered = json.dumps(report, ensure_ascii=False)
    markdown = attestation.render_markdown(report)

    assert str(root) not in rendered
    assert str(root) not in markdown
    for case in report["cases"]:
        for asset in case["assets"]:
            assert not asset["path"].startswith("/")
        assert all(not path.startswith("/") for path in case["unavailable_prerequisites"])
    assert "sources/" in [asset["path"] for asset in _case(report, PLAIN_CASE)["assets"]]


def test_credential_shaped_subprocess_output_is_redacted(tmp_path: Path) -> None:
    outcomes = (
        HarnessOutcome(
            module=attestation.BENCHMARK_TEST_MODULE,
            test=attestation.SOURCE_BACKED_PRIMARY_TEST,
            case_id=PLAIN_CASE,
            outcome="failed",
            message=JWT_PAYLOAD,
        ),
    )

    report = _build(_committed_root(tmp_path), outcomes=outcomes)
    markdown = attestation.render_markdown(report)
    rendered = json.dumps(report, ensure_ascii=False)

    failure = _case(report, PLAIN_CASE)["harness"]["failures"][0]
    assert failure["test"] == attestation.SOURCE_BACKED_PRIMARY_TEST
    assert "eyJhbGciOiJIUzI1NiJ9" not in failure["message"]
    assert "eyJhbGciOiJIUzI1NiJ9" not in rendered
    assert "eyJhbGciOiJIUzI1NiJ9" not in markdown
    assert "harness-check-failed" in _case(report, PLAIN_CASE)["reasons"]


def test_skip_messages_never_carry_a_local_path_into_the_report(
    tmp_path: Path,
) -> None:
    outcomes = (
        HarnessOutcome(
            module=attestation.BENCHMARK_TEST_MODULE,
            test=attestation.SOURCE_BACKED_PRIMARY_TEST,
            case_id=PLAIN_CASE,
            outcome="failed",
            message="/Users/operator/private/benchmarks/newebpay-mpg/sources/spec.md missing",
        ),
    )

    report = _build(_committed_root(tmp_path), outcomes=outcomes)

    message = _case(report, PLAIN_CASE)["harness"]["failures"][0]["message"]
    assert "/Users/operator" not in message
    assert "[REDACTED]" in message


def test_supplier_source_content_never_reaches_the_report(tmp_path: Path) -> None:
    root = _committed_root(tmp_path)
    _stock_operator_assets(root / PLAIN_CASE, source_text=f"# spec\n{SUPPLIER_SECRET}\n")

    report = _build(root)
    markdown = attestation.render_markdown(report)

    assert SUPPLIER_SECRET not in json.dumps(report, ensure_ascii=False)
    assert SUPPLIER_SECRET not in markdown
    assert _case(report, PLAIN_CASE)["assurance"]["prerequisites_available"] is True


def test_case_identity_relative_asset_and_digest_are_preserved(tmp_path: Path) -> None:
    report = _build(_committed_root(tmp_path))
    case = _case(report, SANITIZED_CASE)

    assert case["case_id"] == SANITIZED_CASE
    assert "extraction/inventory.json" in [asset["path"] for asset in case["assets"]]
    assert case["source_reference"]["digest"] == (
        "74ecbad355e8b7d2a051c61257a286a01d06493192404ed967fc5c4390ccc3e0"
    )
    assert case["source_reference"]["path"].startswith("sanitized_sources/")


def test_symlinked_or_existing_output_path_is_rejected_without_partial_output(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "report.json"
    existing.write_text("previous", encoding="utf-8")
    link = tmp_path / "linked.json"
    link.symlink_to(tmp_path / "elsewhere.json")

    with pytest.raises(AttestationError, match="existing output path"):
        attestation.write_exclusive(existing, "new")
    with pytest.raises(AttestationError):
        attestation.write_exclusive(link, "new")

    assert existing.read_text(encoding="utf-8") == "previous"
    assert not (tmp_path / "elsewhere.json").exists()


def test_a_rejected_second_output_leaves_no_partial_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _committed_root(tmp_path)
    monkeypatch.setattr(attestation, "run_harness", lambda *, root: ((), 0))
    monkeypatch.setattr(attestation, "repository_binding", lambda *, root: BINDING)
    markdown_out = tmp_path / "report.md"
    markdown_out.write_text("previous", encoding="utf-8")

    exit_code = attestation.main(
        [
            "--benchmark-root",
            str(root),
            "--json-out",
            str(tmp_path / "report.json"),
            "--markdown-out",
            str(markdown_out),
        ]
    )

    assert exit_code == 1
    assert markdown_out.read_text(encoding="utf-8") == "previous"


# --- command behavior ------------------------------------------------------


def test_command_writes_both_outputs_and_reports_no_source_backed_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _committed_root(tmp_path)
    monkeypatch.setattr(attestation, "run_harness", lambda *, root: ((), 0))
    monkeypatch.setattr(attestation, "repository_binding", lambda *, root: BINDING)
    json_out = tmp_path / "report.json"
    markdown_out = tmp_path / "report.md"

    exit_code = attestation.main(
        [
            "--benchmark-root",
            str(root),
            "--json-out",
            str(json_out),
            "--markdown-out",
            str(markdown_out),
        ]
    )

    report = json.loads(json_out.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["totals"]["source_backed_executed"] == 0
    assert report["totals"]["strict_local_passed"] == 0
    assert report["totals"]["required_cases"] == len(quality_gate.REQUIRED_BENCHMARK_CASES)
    assert markdown_out.read_text(encoding="utf-8").startswith("# Benchmark Attestation")


def test_command_requires_an_output_destination() -> None:
    assert attestation.main([]) == 2


# --- machine-readable execution results ------------------------------------


def test_junit_outcomes_are_read_from_xml_not_from_pytest_prose() -> None:
    outcomes = attestation.parse_junit(
        """<?xml version="1.0" encoding="utf-8"?>
        <testsuites><testsuite name="pytest">
          <testcase classname="tests.test_benchmarks" name="test_benchmark_case[newebpay-mpg]"/>
          <testcase classname="tests.test_benchmarks" name="test_benchmark_case[stripe-basic-rest]">
            <skipped type="pytest.skip" message="sources/ not present"/>
          </testcase>
          <testcase classname="tests.test_benchmarks" name="test_benchmark_score[tappay-backend]">
            <failure message="drift"/>
          </testcase>
          <testcase classname="tests.test_benchmarks" name="test_operation_count"/>
        </testsuite></testsuites>"""
    )

    assert [(outcome.case_id, outcome.outcome) for outcome in outcomes] == [
        ("newebpay-mpg", "passed"),
        ("stripe-basic-rest", "skipped"),
        ("tappay-backend", "failed"),
        (None, "passed"),
    ]
    assert outcomes[1].message == "sources/ not present"
    assert outcomes[3].test == "test_operation_count"


def test_malformed_junit_report_fails_closed() -> None:
    with pytest.raises(AttestationError, match="JUnit report is malformed"):
        attestation.parse_junit("<testsuites>")


def test_named_harness_checks_still_exist() -> None:
    """The three names binding an assurance level to its check.

    A rename must fail here rather than silently downgrade every case to
    "nothing was established", which is the one failure mode a report like this
    cannot tolerate.
    """
    import tests.test_benchmarks as benchmarks
    import tests.test_sanitized_benchmarks as sanitized

    assert callable(getattr(benchmarks, attestation.SOURCE_BACKED_PRIMARY_TEST))
    assert callable(getattr(benchmarks, attestation.EXACT_EVIDENCE_PARITY_TEST))
    assert callable(getattr(sanitized, attestation.SANITIZED_EXACT_EVIDENCE_TEST))
