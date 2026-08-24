from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts import quality_gate
from tests.cli_commands_support import registered_cli_commands


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


def test_excerpt_keeps_the_failure_tail_when_output_is_long():
    excerpt = quality_gate._excerpt("a" * 1_200 + " FAILURE DETAIL", limit=100)

    assert excerpt.startswith("a" * 50)
    assert "...[truncated]..." in excerpt
    assert excerpt.endswith("FAILURE DETAIL")


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


def test_command_plan_sanitized_fixture_mode_includes_dedicated_lane():
    plan = quality_gate.command_plan(strict_local=False, sanitized_fixtures=True)

    assert plan == [
        ("ruff", ["uv", "run", "ruff", "check", "."]),
        ("pytest", ["uv", "run", "pytest", "--cov=loop_apidoc"]),
        (
            "sanitized-fixtures",
            ["uv", "run", "pytest", "tests/test_sanitized_benchmarks.py", "-q"],
        ),
    ]


def test_quality_gate_rejects_combining_strict_local_and_sanitized_fixtures(capsys):
    exit_code = quality_gate.main(["--strict-local", "--sanitized-fixtures"])

    assert exit_code == 2
    assert "cannot be combined" in capsys.readouterr().err


def test_required_benchmark_cases_match_committed_cases():
    cases = quality_gate.required_benchmark_cases()
    benchmark_root = Path(__file__).resolve().parents[1] / "benchmarks"
    committed = {
        case.name
        for case in benchmark_root.iterdir()
        if (case / "extraction" / "inventory.json").is_file()
        and (case / "expected" / "validation.expect.json").is_file()
    }

    assert set(cases) == committed
    assert len(cases) == len(committed)


def test_required_sanitized_benchmark_cases_match_committed_descriptors():
    cases = quality_gate.required_sanitized_benchmark_cases()
    benchmark_root = Path(__file__).resolve().parents[1] / "benchmarks"
    committed = {
        case.name
        for case in benchmark_root.iterdir()
        if (case / "sanitized-fixture.json").is_file()
    }

    assert set(cases) == committed == {"rsg-game-transfer-wallet"}


def test_required_source_derivation_benchmark_cases_match_committed_descriptors():
    cases = quality_gate.required_source_derivation_benchmark_cases()
    benchmark_root = Path(__file__).resolve().parents[1] / "benchmarks"
    committed = {
        case.name
        for case in benchmark_root.iterdir()
        if (case / "source-derivation.json").is_file()
    }

    assert set(cases) == committed == {"ecpay-creditcard-pdf"}


def test_every_cli_command_is_graded_or_explicitly_excluded():
    registered = registered_cli_commands()

    assert "foundry approve" in registered  # sub-app commands are in scope
    assert quality_gate.acquisition_grading_gaps(registered) == {
        "ungraded": [],
        "unknown": [],
    }


def test_acquisition_grading_gaps_reports_an_ungraded_new_command():
    registered = set(quality_gate.SOURCE_ACQUISITION_EVIDENCE_TIERS)
    registered |= set(quality_gate.NON_ACQUISITION_CLI_COMMANDS)
    registered.add("fetch-supplier-portal")

    assert quality_gate.acquisition_grading_gaps(registered) == {
        "ungraded": ["fetch-supplier-portal"],
        "unknown": [],
    }


def test_acquisition_grading_gaps_reports_a_command_that_no_longer_exists():
    registered = set(quality_gate.SOURCE_ACQUISITION_EVIDENCE_TIERS)
    registered |= set(quality_gate.NON_ACQUISITION_CLI_COMMANDS)
    registered.discard("select-url")

    assert quality_gate.acquisition_grading_gaps(registered) == {
        "ungraded": [],
        "unknown": ["select-url"],
    }


def test_acquisition_tiers_use_the_three_documented_labels():
    for command, tiers in quality_gate.SOURCE_ACQUISITION_EVIDENCE_TIERS.items():
        assert tiers, command
        assert len(set(tiers)) == len(tiers), command
        assert set(tiers) <= set(quality_gate.ACQUISITION_EVIDENCE_TIERS), command

    assert quality_gate.ACQUISITION_EVIDENCE_TIERS == (
        "source-backed",
        "not validated against a real source",
        "outside the harness by construction",
    )


def test_every_excluded_command_carries_a_reason():
    for command, reason in quality_gate.NON_ACQUISITION_CLI_COMMANDS.items():
        assert reason.strip(), command


def test_no_command_is_both_graded_and_excluded():
    graded = set(quality_gate.SOURCE_ACQUISITION_EVIDENCE_TIERS)
    excluded = set(quality_gate.NON_ACQUISITION_CLI_COMMANDS)

    assert graded & excluded == set()


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


def test_missing_benchmark_source_quality_reports_incomplete_packages(tmp_path):
    root = tmp_path / "benchmarks"
    complete = root / "audited" / "source-quality"
    complete.mkdir(parents=True)
    for name in quality_gate.BENCHMARK_QUALITY_FILES:
        (complete / name).write_text("{}", encoding="utf-8")
    partial = root / "half-audited" / "source-quality"
    partial.mkdir(parents=True)
    (partial / "source-quality-report.json").write_text("{}", encoding="utf-8")

    missing = quality_gate.missing_benchmark_source_quality(
        benchmark_root=root,
        cases=["audited", "half-audited", "unaudited"],
    )

    assert missing == ["half-audited", "unaudited"]


def test_missing_benchmark_source_derivation_reports_absent_originals_only(tmp_path):
    root = tmp_path / "benchmarks"
    restored = root / "restored"
    restored.mkdir(parents=True)
    (restored / "source-derivation.json").write_text(
        json.dumps({"original_document": {"path": "raw/doc.pdf"}}),
        encoding="utf-8",
    )
    (restored / "raw").mkdir()
    (restored / "raw" / "doc.pdf").write_text("pdf bytes", encoding="utf-8")

    not_restored = root / "not-restored"
    not_restored.mkdir()
    (not_restored / "source-derivation.json").write_text(
        json.dumps({"original_document": {"path": "raw/doc.pdf"}}),
        encoding="utf-8",
    )

    # A missing/broken descriptor is a different failure mode (see
    # test_invalid_benchmark_source_derivation_reports_broken_descriptors below)
    # and must never be reported here as "original missing".
    no_descriptor = root / "no-descriptor"
    no_descriptor.mkdir()

    missing = quality_gate.missing_benchmark_source_derivation(
        benchmark_root=root,
        cases=["restored", "not-restored", "no-descriptor"],
    )

    assert missing == ["not-restored"]


def test_invalid_benchmark_source_derivation_reports_broken_descriptors(tmp_path):
    root = tmp_path / "benchmarks"
    valid = root / "valid"
    valid.mkdir(parents=True)
    (valid / "source-derivation.json").write_text(
        json.dumps({"original_document": {"path": "raw/doc.pdf"}}),
        encoding="utf-8",
    )

    no_descriptor = root / "no-descriptor"
    no_descriptor.mkdir()

    bad_json = root / "bad-json"
    bad_json.mkdir()
    (bad_json / "source-derivation.json").write_text("{ not json", encoding="utf-8")

    missing_field = root / "missing-field"
    missing_field.mkdir()
    (missing_field / "source-derivation.json").write_text(
        json.dumps({"original_document": {}}), encoding="utf-8"
    )

    escaping = root / "escaping"
    escaping.mkdir()
    (escaping / "source-derivation.json").write_text(
        json.dumps({"original_document": {"path": "../../etc/passwd"}}),
        encoding="utf-8",
    )

    invalid = quality_gate.invalid_benchmark_source_derivation(
        benchmark_root=root,
        cases=["valid", "no-descriptor", "bad-json", "missing-field", "escaping"],
    )

    assert invalid == ["no-descriptor", "bad-json", "missing-field", "escaping"]


def test_strict_local_does_not_accept_sanitized_sources_as_originals(tmp_path):
    root = tmp_path / "benchmarks"
    sanitized = root / "fixture-only" / "sanitized_sources"
    sanitized.mkdir(parents=True)
    (sanitized / "manual.md").write_text("retained evidence", encoding="utf-8")

    missing = quality_gate.missing_benchmark_sources(
        benchmark_root=root,
        cases=["fixture-only"],
    )

    assert missing == ["fixture-only"]


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


# --- File-I/O exit inventory (issue #125) ------------------------------------


def _write_module(tmp_path: Path, name: str, body: str) -> Path:
    package = tmp_path / "pkg"
    package.mkdir(exist_ok=True)
    (package / name).write_text(body, encoding="utf-8")
    return package


def test_every_module_that_writes_is_in_the_file_io_inventory():
    scanned = quality_gate.modules_with_file_writes()

    assert "loop_apidoc/validate/report.py" in scanned  # was missing from AGENTS.md
    assert "loop_apidoc/atomic_publish.py" in scanned
    assert quality_gate.file_io_registry_gaps(scanned) == {
        "unregistered": [],
        "stale": [],
    }


def test_file_io_registry_gaps_reports_both_directions():
    registered = set(quality_gate.FILE_IO_EXIT_MODULES)

    assert quality_gate.file_io_registry_gaps(
        (registered | {"loop_apidoc/new_writer.py"}) - {"loop_apidoc/run/persist.py"}
    ) == {
        "unregistered": ["loop_apidoc/new_writer.py"],
        "stale": ["loop_apidoc/run/persist.py"],
    }


def test_scanner_ignores_str_replace_and_other_pure_calls(tmp_path):
    package = _write_module(
        tmp_path,
        "pure.py",
        "def f(text: str, items):\n"
        "    joined = text.replace('a', 'b')\n"
        "    data = open('x.txt').read()\n"
        "    return sorted(items), joined, data\n",
    )

    assert quality_gate.modules_with_file_writes(package_root=package, relative_to=package) == ()


def test_scanner_recognises_the_documented_write_calls(tmp_path):
    package = _write_module(
        tmp_path,
        "writer.py",
        "import os\nimport shutil\nfrom pathlib import Path\n\n"
        "def f(p: Path, tmp: Path):\n"
        "    p.parent.mkdir(parents=True, exist_ok=True)\n"
        "    p.write_text('x', encoding='utf-8')\n"
        "    tmp.replace(p)\n"
        "    os.replace(tmp, p)\n"
        "    shutil.rmtree(p)\n"
        "    with open(p, 'w', encoding='utf-8') as fh:\n"
        "        fh.write('x')\n",
    )

    assert quality_gate.modules_with_file_writes(
        package_root=package, relative_to=package
    ) == ("writer.py",)


def test_scanner_recognises_an_exclusive_binary_open(tmp_path):
    package = _write_module(
        tmp_path,
        "exclusive.py",
        "from pathlib import Path\n\n"
        "def f(p: Path):\n"
        "    with p.open('xb') as fh:\n"
        "        fh.write(b'x')\n",
    )

    assert quality_gate.modules_with_file_writes(
        package_root=package, relative_to=package
    ) == ("exclusive.py",)


def test_scanner_counts_a_tempfile_staging_call(tmp_path):
    # Eight inventory modules stage through tempfile; each is currently caught
    # by another call in the same file, so this shape must count on its own.
    package = _write_module(
        tmp_path,
        "staging.py",
        "import os\nimport tempfile\n\n"
        "def f() -> None:\n"
        "    fd, name = tempfile.mkstemp()\n"
        "    os.write(fd, b'x')\n",
    )

    assert quality_gate.modules_with_file_writes(
        package_root=package, relative_to=package
    ) == ("staging.py",)


def test_scanner_requires_a_registered_low_level_ctypes_entrypoint(tmp_path, monkeypatch):
    package = _write_module(
        tmp_path,
        "expected.py",
        "def f(renameat2):\n"
        "    return renameat2(1, b'from', 1, b'to', 1)\n",
    )
    _write_module(
        tmp_path,
        "stale.py",
        "def f() -> None:\n"
        "    return None\n",
    )
    monkeypatch.setattr(
        quality_gate,
        "LOW_LEVEL_FILESYSTEM_WRITE_ENTRYPOINTS",
        {
            "expected.py": frozenset({"renameat2"}),
            "stale.py": frozenset({"renameat2"}),
        },
    )

    assert quality_gate.modules_with_file_writes(
        package_root=package, relative_to=package
    ) == ("expected.py",)


def test_scanner_ignores_dataclasses_replace_and_a_pathlike_open_argument(tmp_path):
    package = _write_module(
        tmp_path,
        "lookalikes.py",
        "import dataclasses\nimport zipfile\n\n"
        "def f(obj, archive: zipfile.ZipFile):\n"
        "    updated = dataclasses.replace(obj)\n"
        "    member = archive.open('word/document.xml')\n"
        "    return updated, member\n",
    )

    assert quality_gate.modules_with_file_writes(
        package_root=package, relative_to=package
    ) == ()


def test_scanner_prefix_does_not_depend_on_how_the_root_was_spelled():
    absolute = Path(__file__).resolve().parents[1] / "loop_apidoc"

    assert quality_gate.modules_with_file_writes(
        package_root=absolute
    ) == quality_gate.modules_with_file_writes()
