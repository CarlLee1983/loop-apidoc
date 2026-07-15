from __future__ import annotations

from dataclasses import dataclass

import pytest

from scripts import quality_gate


@dataclass
class FakeResult:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def test_run_step_prints_pass_on_zero_exit(capsys):
    calls: list[list[str]] = []

    def runner(cmd: list[str]) -> FakeResult:
        calls.append(cmd)
        return FakeResult(stdout="ok")

    quality_gate.run_step("ruff", ["uv", "run", "ruff", "check", "."], runner=runner)

    assert calls == [["uv", "run", "ruff", "check", "."]]
    assert "[quality-gate] PASS ruff" in capsys.readouterr().out


def test_run_step_raises_with_output_excerpt_on_failure():
    def runner(cmd: list[str]) -> FakeResult:
        return FakeResult(returncode=7, stdout="stdout text", stderr="stderr text")

    with pytest.raises(quality_gate.QualityGateFailure) as exc:
        quality_gate.run_step("pytest", ["uv", "run", "pytest"], runner=runner)

    message = str(exc.value)
    assert "pytest failed with exit code 7" in message
    assert "stdout text" in message
    assert "stderr text" in message


def test_command_plan_default_mode():
    plan = quality_gate.command_plan(strict_local=False)
    assert plan == [
        ("ruff", ["uv", "run", "ruff", "check", "."]),
        ("pytest", ["uv", "run", "pytest", "--cov=loop_apidoc"]),
    ]


def test_command_plan_strict_local_includes_benchmarks():
    plan = quality_gate.command_plan(strict_local=True)
    assert plan == [
        ("ruff", ["uv", "run", "ruff", "check", "."]),
        ("pytest", ["uv", "run", "pytest", "--cov=loop_apidoc"]),
        ("benchmarks", ["uv", "run", "pytest", "tests/test_benchmarks.py", "-q"]),
    ]


def test_required_benchmark_cases_lists_committed_cases():
    cases = quality_gate.required_benchmark_cases()
    assert {"newebpay-mpg", "apis-guru-baseline", "tappay-backend",
            "line-pay-online-v3", "stripe-basic-rest", "cybersource-payments",
            "github-webhooks", "paypal-webhooks-incomplete",
            "ecpay-creditcard-pdf", "adyen-payments-multimethod"} <= set(cases)


def test_missing_benchmark_sources_reports_absent_or_empty_dirs(tmp_path):
    root = tmp_path / "benchmarks"
    (root / "has-source" / "sources").mkdir(parents=True)
    (root / "has-source" / "sources" / "manual.md").write_text("ok", encoding="utf-8")
    (root / "empty-source" / "sources").mkdir(parents=True)

    missing = quality_gate.missing_benchmark_sources(
        benchmark_root=root,
        cases=["has-source", "empty-source", "absent-source"],
    )

    assert missing == ["empty-source", "absent-source"]


def test_missing_benchmark_sources_accepts_nested_only_sources(tmp_path):
    root = tmp_path / "benchmarks"
    nested = root / "nested-source" / "sources" / "docs"
    nested.mkdir(parents=True)
    (nested / "spec.pdf").write_text("ok", encoding="utf-8")

    missing = quality_gate.missing_benchmark_sources(
        benchmark_root=root,
        cases=["nested-source"],
    )

    assert missing == []


@pytest.mark.parametrize("stdout", [
    "10 passed, 1 skipped in 0.20s",
    "........s..",
    "SKIPPED [1] sources missing",
])
def test_has_benchmark_skips_detects_skip_signals(stdout):
    assert quality_gate.has_benchmark_skips(stdout)


def test_has_benchmark_skips_accepts_no_skip_output():
    assert not quality_gate.has_benchmark_skips("11 passed in 0.20s\n...........")


def test_has_benchmark_skips_rejects_non_pytest_word():
    # "esp" is a subset of the pytest result-char set and contains an "s", but it
    # is not a genuine progress line; it must not be treated as a skip signal.
    assert not quality_gate.has_benchmark_skips("esp")


def test_adversarial_smoke_detects_secret_leaked_to_stderr():
    secret = "TOP SECRET DO NOT READ"

    def runner(cmd: list[str]) -> FakeResult:
        if "manifest" in cmd:
            # status surfaces the expected signal on stdout, but the secret leaks
            # into stderr — the gate must still catch it.
            return FakeResult(returncode=0, stdout='"status": "unreadable"', stderr=secret)
        return FakeResult(returncode=0, stdout='{"ok": true, "status": "PASS"}')

    results = quality_gate.run_adversarial_cli_smoke(runner=runner)
    adv006 = next(r for r in results if r.scenario_id == "ADV-006")

    assert not adv006.ok


def test_run_step_raises_quality_gate_failure_on_timeout():
    import subprocess

    cmd = ["uv", "run", "pytest"]

    def runner(c: list[str]) -> FakeResult:
        raise subprocess.TimeoutExpired(c, 600)

    with pytest.raises(quality_gate.QualityGateFailure) as exc:
        quality_gate.run_step("pytest", cmd, runner=runner)

    message = str(exc.value)
    assert "pytest" in message
    assert "TimeoutExpired" not in type(exc.value).__name__


def test_scenario_result_requires_expected_exit_and_signal():
    result = quality_gate.ScenarioResult(
        scenario_id="ADV-001",
        exit_code=2,
        expected_exit=2,
        signal="inventory.json 不是合法 JSON",
        expected_signal="inventory.json 不是合法 JSON",
        cleanup_ok=True,
    )
    assert result.ok


def test_scenario_result_fails_on_exit_mismatch():
    result = quality_gate.ScenarioResult(
        scenario_id="ADV-001",
        exit_code=1,
        expected_exit=2,
        signal="inventory.json 不是合法 JSON",
        expected_signal="inventory.json 不是合法 JSON",
        cleanup_ok=True,
    )
    assert not result.ok


def test_scenario_result_fails_on_missing_signal():
    result = quality_gate.ScenarioResult(
        scenario_id="ADV-001",
        exit_code=2,
        expected_exit=2,
        signal="different",
        expected_signal="inventory.json 不是合法 JSON",
        cleanup_ok=True,
    )
    assert not result.ok
