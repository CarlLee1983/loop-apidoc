from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass


Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


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


def run_step(name: str, cmd: list[str], *, runner: Runner = _default_runner) -> None:
    print(f"[quality-gate] {name}: {' '.join(cmd)}")
    result = runner(cmd)
    if result.returncode != 0:
        raise QualityGateFailure(
            f"{name} failed with exit code {result.returncode}\n"
            f"stdout:\n{_excerpt(result.stdout)}\n"
            f"stderr:\n{_excerpt(result.stderr)}"
        )
    print(f"[quality-gate] PASS {name}")


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
        for name, cmd in command_plan(strict_local=args.strict_local):
            run_step(name, cmd)
    except QualityGateFailure as exc:
        print(f"[quality-gate] FAILED\n{exc}", file=sys.stderr)
        return 1
    print("[quality-gate] COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
