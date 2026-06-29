from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]

BENCHMARK_ROOT = Path("benchmarks")
REQUIRED_BENCHMARK_CASES = (
    "newebpay-mpg",
    "apis-guru-baseline",
    "tappay-backend",
    "line-pay-online-v3",
    "stripe-basic-rest",
    "cybersource-payments",
    "github-webhooks",
    "paypal-webhooks-incomplete",
    "ecpay-creditcard-pdf",
    "adyen-payments-multimethod",
)


class QualityGateFailure(RuntimeError):
    """Raised when a quality gate step fails."""


@dataclass(frozen=True)
class StepResult:
    name: str
    command: list[str]


def _default_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, timeout=120)


def _excerpt(text: str, limit: int = 1200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def required_benchmark_cases() -> tuple[str, ...]:
    return REQUIRED_BENCHMARK_CASES


def missing_benchmark_sources(
    *,
    benchmark_root: Path = BENCHMARK_ROOT,
    cases: tuple[str, ...] | list[str] = REQUIRED_BENCHMARK_CASES,
) -> list[str]:
    missing: list[str] = []
    for case in cases:
        src = benchmark_root / case / "sources"
        if not src.is_dir() or not any(path.is_file() for path in src.iterdir()):
            missing.append(case)
    return missing


def has_benchmark_skips(stdout: str) -> bool:
    if "skipped" in stdout.lower():
        return True
    # pytest progress line: only result chars; an "s" marks a skipped test
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped and set(stripped) <= set(".sfexXpP") and "s" in stripped:
            return True
    return False


def run_step(name: str, cmd: list[str], *, runner: Runner = _default_runner) -> subprocess.CompletedProcess[str]:
    print(f"[quality-gate] {name}: {' '.join(cmd)}")
    result = runner(cmd)
    if result.returncode != 0:
        raise QualityGateFailure(
            f"{name} failed with exit code {result.returncode}\n"
            f"stdout:\n{_excerpt(result.stdout)}\n"
            f"stderr:\n{_excerpt(result.stderr)}"
        )
    print(f"[quality-gate] PASS {name}")
    return result


def command_plan(*, strict_local: bool) -> list[tuple[str, list[str]]]:
    return [
        ("ruff", ["uv", "run", "ruff", "check", "."]),
        ("pytest", ["uv", "run", "pytest"]),
        ("benchmarks", ["uv", "run", "pytest", "tests/test_benchmarks.py", "-q"]),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-local", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.strict_local:
            missing = missing_benchmark_sources()
            if missing:
                raise QualityGateFailure(
                    "strict-local benchmark sources missing or empty: "
                    + ", ".join(missing)
                )
        benchmark_result: subprocess.CompletedProcess[str] | None = None
        for name, cmd in command_plan(strict_local=args.strict_local):
            result = run_step(name, cmd)
            if name == "benchmarks":
                benchmark_result = result
        if args.strict_local and benchmark_result is not None:
            combined = f"{benchmark_result.stdout}\n{benchmark_result.stderr}"
            if has_benchmark_skips(combined):
                raise QualityGateFailure(
                    "strict-local benchmark run reported skips; all benchmark cases "
                    "must execute where local sources are present"
                )
    except QualityGateFailure as exc:
        print(f"[quality-gate] FAILED\n{exc}", file=sys.stderr)
        return 1
    print("[quality-gate] COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
