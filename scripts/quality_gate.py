from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
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


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    exit_code: int
    expected_exit: int
    signal: str
    expected_signal: str
    cleanup_ok: bool

    @property
    def ok(self) -> bool:
        return (
            self.exit_code == self.expected_exit
            and self.expected_signal in self.signal
            and self.cleanup_ok
        )


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


BASE_INVENTORY = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "manual.md"}],
    "security_schemes": [],
    "schemas": [],
    "errors": [],
    "operational": [{"topic": "Authentication", "details": "public API", "source": "manual.md"}],
    "endpoints": [{"method": "GET", "path": "/ping", "summary": "健康檢查",
                   "source": "manual.md"}],
    "missing": [],
}

BASE_ENDPOINT = {
    "method": "GET",
    "path": "/ping",
    "parameters": [],
    "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [],
    "missing": [],
    "source": "manual.md",
}


def _write_valid_fixture(root: Path) -> tuple[Path, Path, Path]:
    sources = root / "sources"
    extraction = root / "extraction"
    endpoints = extraction / "endpoints"
    out = root / "out"
    sources.mkdir(parents=True)
    endpoints.mkdir(parents=True)
    (sources / "manual.md").write_text("# Demo API\nGET /ping\npublic API", encoding="utf-8")
    (extraction / "inventory.json").write_text(
        json.dumps(BASE_INVENTORY, ensure_ascii=False), encoding="utf-8")
    (endpoints / "ep0.json").write_text(
        json.dumps(BASE_ENDPOINT, ensure_ascii=False), encoding="utf-8")
    return sources, extraction, out


def run_adversarial_cli_smoke(*, runner: Runner = _default_runner) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    with tempfile.TemporaryDirectory(prefix="loop-apidoc-adv-") as td:
        root = Path(td)

        sources, extraction, out = _write_valid_fixture(root / "normal")
        cmd = ["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
               "--extraction", str(extraction), "--output", str(out), "--json"]
        res = runner(cmd)
        signal = res.stdout
        try:
            payload = json.loads(res.stdout)
            signal = f"ok={payload['ok']} status={payload['status']}"
        except json.JSONDecodeError:
            pass
        results.append(ScenarioResult("ADV-001", res.returncode, 0, signal, "ok=True", out.exists()))

        sources, extraction, out = _write_valid_fixture(root / "bad-json")
        (extraction / "inventory.json").write_text("{ not json", encoding="utf-8")
        res = runner(["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
                      "--extraction", str(extraction), "--output", str(out), "--json"])
        results.append(ScenarioResult(
            "ADV-002", res.returncode, 2, res.stderr,
            "inventory.json 不是合法 JSON", not out.exists()))

        sources, extraction, out = _write_valid_fixture(root / "localized-keys")
        inventory = dict(BASE_INVENTORY)
        inventory["schemas"] = [{"name": "Bad", "fields": [{"名稱": "id", "型別": "string"}],
                                 "source": "manual.md"}]
        (extraction / "inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
        res = runner(["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
                      "--extraction", str(extraction), "--output", str(out), "--json"])
        results.append(ScenarioResult(
            "ADV-003", res.returncode, 2, res.stderr,
            "schemas[0].fields[0]", not out.exists()))

        sources, extraction, out = _write_valid_fixture(root / "bad-integration")
        (extraction / "integration.json").write_text("[]", encoding="utf-8")
        res = runner(["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
                      "--extraction", str(extraction), "--output", str(out), "--json"])
        results.append(ScenarioResult(
            "ADV-004", res.returncode, 2, res.stderr,
            "integration.json 必須是 JSON 物件", not out.exists()))

        run_dir = root / "incomplete-run"
        run_dir.mkdir()
        res = runner(["uv", "run", "loop-apidoc", "validate", "--output", str(run_dir)])
        report_path = run_dir / "validation" / "report.json"
        signal = res.stdout
        if report_path.exists():
            signal += report_path.read_text(encoding="utf-8")
        results.append(ScenarioResult(
            "ADV-005", res.returncode, 1, signal,
            "OUTPUT_MISMATCH", report_path.exists()))

        srcroot = root / "symlink-src"
        srcroot.mkdir()
        (srcroot / "good.md").write_text("# ok", encoding="utf-8")
        secret = root / "outside-secret.md"
        secret.write_text("TOP SECRET DO NOT READ", encoding="utf-8")
        os.symlink(secret, srcroot / "leak.md")
        res = runner(["uv", "run", "loop-apidoc", "manifest", "--sources", str(srcroot)])
        signal = res.stdout
        results.append(ScenarioResult(
            "ADV-006", res.returncode, 0, signal,
            '"status": "unreadable"', True))

    return results


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
        print("[quality-gate] adversarial CLI smoke")
        scenario_results = run_adversarial_cli_smoke()
        failed = [result for result in scenario_results if not result.ok]
        if failed:
            lines = [
                f"{result.scenario_id}: exit {result.exit_code}/{result.expected_exit}; "
                f"signal={_excerpt(result.signal, 300)!r}; cleanup_ok={result.cleanup_ok}"
                for result in failed
            ]
            raise QualityGateFailure("adversarial CLI smoke failed:\n" + "\n".join(lines))
        print(f"[quality-gate] PASS adversarial CLI smoke ({len(scenario_results)} scenarios)")
    except QualityGateFailure as exc:
        print(f"[quality-gate] FAILED\n{exc}", file=sys.stderr)
        return 1
    print("[quality-gate] COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
