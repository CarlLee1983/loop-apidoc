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
        ("pytest", ["uv", "run", "pytest"]),
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


@pytest.mark.parametrize("stdout", [
    "10 passed, 1 skipped in 0.20s",
    "........s..",
    "SKIPPED [1] sources missing",
])
def test_has_benchmark_skips_detects_skip_signals(stdout):
    assert quality_gate.has_benchmark_skips(stdout)


def test_has_benchmark_skips_accepts_no_skip_output():
    assert not quality_gate.has_benchmark_skips("11 passed in 0.20s\n...........")
