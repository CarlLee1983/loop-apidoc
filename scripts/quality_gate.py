from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class _RunResult(Protocol):
    """Structural contract for a finished command: the bits the gate reads."""

    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str]], _RunResult]

STEP_TIMEOUT_SECONDS = 600

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
    "jili-legacy-gaming-pdf",
    "funkygames-transfer-operator",
    "rsg-game-transfer-wallet",
)
SANITIZED_BENCHMARK_CASES = ("rsg-game-transfer-wallet",)
# Cases whose committed `sources/*.md` is asserted to be pymupdf4llm's actual
# output for a specific, dated, checksummed original PDF — not merely a hand
# transcription. See `source-derivation.json` in each listed case.
SOURCE_DERIVATION_BENCHMARK_CASES = ("ecpay-creditcard-pdf",)


# --- Acquisition-path evidence grading (issue #121) -------------------------
#
# The three labels #112 wrote into both READMEs and both operator manuals. The
# documents are the human-readable presentation; this registry is the truth a
# test can check, so a new acquisition command cannot ship unlabelled the way
# `.docx` and GitBook did for most of a version.
ACQUISITION_EVIDENCE_TIERS = (
    "source-backed",
    "not validated against a real source",
    "outside the harness by construction",
)

# **The criterion**, so this list does not itself become something to remember:
# a CLI command is an *acquisition path* when it brings supplier material into
# the local, manifest-bindable corpus, or establishes that corpus. Everything
# else is excluded by name below with the reason. Exhaustive classification is
# the mechanism — `acquisition_grading_gaps` fails on a command that is in
# neither mapping, so a new command forces the decision rather than inheriting
# a default. Sub-app commands (`foundry <cmd>`, `feedback <cmd>`) are keyed by
# their full invocation and excluded individually for the same reason: naming
# the group once would let a later `foundry fetch-portal` ship ungraded.
#
# A command carries *every* label its branches earn, not the strongest one — a
# tuple, because `preprocess` and `cache-gitbook-llms` are each in two states at
# once and recording only one is how `.docx` stayed unlabelled through #99.
SOURCE_ACQUISITION_EVIDENCE_TIERS = {
    "manifest": ("source-backed",),
    # PDF is source-backed; the `.docx` branch of the same command has never
    # carried a real Word delivery.
    "preprocess": ("source-backed", "not validated against a real source"),
    "normalize-html-snapshot": ("source-backed",),
    "import-supplementary-note": ("not validated against a real source",),
    "import-rendered-url": ("not validated against a real source",),
    "select-url": ("not validated against a real source",),
    "related-url-pages": ("not validated against a real source",),
    "catalog-url": ("outside the harness by construction",),
    "cache-url-pages": ("outside the harness by construction",),
    "cache-url-entry": ("outside the harness by construction",),
    "snapshot-openapi-url": ("outside the harness by construction",),
    # No real GitBook site has gone through end to end, and it is itself a
    # network acquisition. Only the second label is removable by a source.
    "cache-gitbook-llms": (
        "not validated against a real source",
        "outside the harness by construction",
    ),
}

_GOVERNS_IMPORTED_ASSETS = "governs already-imported assets; reads no supplier document"

NON_ACQUISITION_CLI_COMMANDS = {
    "extract-markdown-drafts": "reads corpus already acquired; writes drafts, not sources",
    "scaffold-extraction": "projects drafts into extraction JSON; acquires nothing",
    "inspect-source-risk": "pre-agent gate over an existing manifest",
    "assess-sources": "quality gate over an existing manifest",
    "verify-extraction": "extraction input gate",
    "assemble": "assembles agent-written JSON into a run",
    "validate": "revalidates a completed run dir",
    "score": "scores a completed run dir",
    "evaluate": "compares two completed runs",
    "diff": "compares two completed runs",
    "review": "local human review workbench over a candidate",
    "record-fingerprint": "records a completed run's source baseline",
    "check-freshness": "compares current signals with a baseline fingerprint",
    "check-freshness-batch": "fans check-freshness over a watchlist",
    "governance-scan": "classifies a batch freshness scan",
    "governance-review-plan": "plans review work from a governance trigger",
    "foundry init": _GOVERNS_IMPORTED_ASSETS,
    "foundry import": "imports a completed run dir, not a source",
    "foundry approve": _GOVERNS_IMPORTED_ASSETS,
    "foundry list": _GOVERNS_IMPORTED_ASSETS,
    "foundry current": _GOVERNS_IMPORTED_ASSETS,
    "feedback assess": "reads normalized observations, not sources",
    "feedback propose": _GOVERNS_IMPORTED_ASSETS,
    "feedback submit": _GOVERNS_IMPORTED_ASSETS,
    "feedback review": _GOVERNS_IMPORTED_ASSETS,
    "feedback approve": _GOVERNS_IMPORTED_ASSETS,
    "feedback compose": _GOVERNS_IMPORTED_ASSETS,
    "feedback current": _GOVERNS_IMPORTED_ASSETS,
    "feedback provider-erratum": "hands off a digest-verified erratum; performs no provider I/O",
}


def acquisition_grading_gaps(commands: Iterable[str]) -> dict[str, list[str]]:
    """Both directions of drift between the CLI and the two mappings above:
    `ungraded` is a registered command in neither mapping, `unknown` is a
    mapped command the CLI no longer registers. Sorted, so a failure reads the
    same on every machine."""
    classified = set(SOURCE_ACQUISITION_EVIDENCE_TIERS) | set(NON_ACQUISITION_CLI_COMMANDS)
    registered = set(commands)
    return {
        "ungraded": sorted(registered - classified),
        "unknown": sorted(classified - registered),
    }


# --- File-I/O exit inventory (issue #125) -----------------------------------
#
# AGENTS.md's "File-I/O exits" paragraph closes with "Every other module is pure
# functions", which makes it a claim of exhaustiveness that nothing checked —
# ten writers had accumulated outside it. The paragraph stays prose for humans;
# this inventory is what a test can compare against the code.
#
# **The criterion**: a module is a file-I/O exit when it *calls* something that
# creates, writes, moves, or removes a filesystem entry. Mechanically that is
# the groups below, and nothing else — a module that only reads, or that hands
# a path to another module, is pure by this measure (`review/workflow.py`
# persists through `foundry/`'s writers and is therefore not listed).
#
# `os.open` is deliberately NOT a write call: it creates only with `O_CREAT`,
# and two read-side exits (`docx_normalization.py`, `source_risk/inspect.py`)
# open read-only descriptors with it. The write that follows shows up as
# `os.write` / `os.fdopen`, which are listed, so nothing escapes by that route.
#
# The constants live here for co-location with the criterion; enforcement is
# `test_every_module_that_writes_is_in_the_file_io_inventory`, not `main()` —
# the same split as `acquisition_grading_gaps` above.
PATH_WRITE_METHODS = frozenset(
    {
        "write_text",
        "write_bytes",
        "touch",
        "mkdir",
        "rmdir",
        "unlink",
        "rename",
        "symlink_to",
        "hardlink_to",
    }
)
OS_WRITE_FUNCTIONS = {
    "os": frozenset(
        {
            "makedirs",
            "mkdir",
            "remove",
            "removedirs",
            "rename",
            "renames",
            "replace",
            "unlink",
            "link",
            "symlink",
            "fdopen",
            "truncate",
            "chmod",
        }
    ),
    "shutil": frozenset(
        {"copy", "copy2", "copyfile", "copytree", "move", "rmtree", "make_archive"}
    ),
    # Every `tempfile` entry point that materializes a real path. Eight modules
    # in the inventory stage through one of these; each is currently caught by
    # some other call in the same file, so a module that staged with `mkstemp`
    # and wrote through the raw descriptor would otherwise pass the gate.
    "tempfile": frozenset(
        {
            "mkstemp",
            "mkdtemp",
            "NamedTemporaryFile",
            "TemporaryFile",
            "TemporaryDirectory",
            "SpooledTemporaryFile",
        }
    ),
}
OS_WRITE_FUNCTIONS["os"] |= frozenset({"write", "ftruncate", "mkfifo"})
# Some platform filesystem syscalls are reached through dynamically loaded C
# symbols. AST can still see the subsequently called local symbol, so register
# its exact names rather than exempting the whole module: a stale exception then
# falls out of the scanned result and the inventory reports it as stale.
LOW_LEVEL_FILESYSTEM_WRITE_ENTRYPOINTS = {
    "loop_apidoc/atomic_publish.py": frozenset(
        {"renameatx_np", "renameat2", "syscall"}
    )
}
WRITE_OPEN_MODE_CHARS = "wax+"
# A mode string is short and drawn from this alphabet. Without the shape check
# any `.open("word/document.xml")` or `.open("https://…/ax")` reads as a write,
# because the name happens to contain `x` or `a`.
_MODE_ALPHABET = set("rwaxbt+U")
# `dataclasses.replace(obj)` is a one-argument `replace` that touches no file.
NON_PATH_REPLACE_RECEIVERS = frozenset({"dataclasses", "copy", "typing"})

FILE_IO_EXIT_MODULES = (
    "loop_apidoc/atomic_publish.py",
    "loop_apidoc/adapters/local.py",
    "loop_apidoc/agentcli/assemble.py",
    "loop_apidoc/agentcli/preprocess.py",
    "loop_apidoc/agentcli/strict.py",
    "loop_apidoc/cli.py",
    "loop_apidoc/descriptor_output.py",
    "loop_apidoc/diff/report.py",
    "loop_apidoc/docx_publish.py",
    "loop_apidoc/evaluation/report.py",
    "loop_apidoc/extraction/store.py",
    "loop_apidoc/extraction_scaffold/write.py",
    "loop_apidoc/feedback/report.py",
    "loop_apidoc/focus/report.py",
    "loop_apidoc/foundry/descriptor_io.py",
    "loop_apidoc/foundry/descriptor_namespace.py",
    "loop_apidoc/foundry/descriptor_tree.py",
    "loop_apidoc/foundry/governed.py",
    "loop_apidoc/foundry/head_io.py",
    "loop_apidoc/foundry/store.py",
    "loop_apidoc/freshness/record.py",
    "loop_apidoc/freshness/report.py",
    "loop_apidoc/generate/writer.py",
    "loop_apidoc/gitbook_llms.py",
    "loop_apidoc/governance/report.py",
    "loop_apidoc/governance/review_plan.py",
    "loop_apidoc/governance/snapshot.py",
    "loop_apidoc/html_snapshot.py",
    "loop_apidoc/openapi_snapshot.py",
    "loop_apidoc/preparation/report.py",
    "loop_apidoc/rendered_url.py",
    "loop_apidoc/run/persist.py",
    "loop_apidoc/score/report.py",
    "loop_apidoc/shadow/report.py",
    "loop_apidoc/source_quality/report.py",
    "loop_apidoc/source_risk/report.py",
    "loop_apidoc/supplementary_note.py",
    "loop_apidoc/url_corpus.py",
    "loop_apidoc/validate/report.py",
)


def _looks_like_mode(value: object) -> bool:
    """Whether a literal is shaped like an open mode. A path or URL that merely
    contains `w`/`a`/`x` is not: `.open("word/document.xml")` must not read as a
    write."""
    return (
        isinstance(value, str)
        and 0 < len(value) <= 4
        and set(value) <= _MODE_ALPHABET
        and any(c in value for c in WRITE_OPEN_MODE_CHARS)
    )


def _opens_for_writing(call: ast.Call, *, mode_position: int) -> bool:
    """Whether an `open()`/`Path.open()` call names a write mode. Only the one
    positional slot that can hold a mode is inspected — scanning every argument
    turned any string containing `x` into a write. A non-literal mode reads as
    read-only rather than being guessed at."""
    if len(call.args) > mode_position:
        candidate = call.args[mode_position]
        if isinstance(candidate, ast.Constant) and _looks_like_mode(candidate.value):
            return True
    return any(
        keyword.arg == "mode"
        and isinstance(keyword.value, ast.Constant)
        and _looks_like_mode(keyword.value.value)
        for keyword in call.keywords
    )


def _call_writes(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == "open" and _opens_for_writing(call, mode_position=1)
    if not isinstance(func, ast.Attribute):
        return False
    receiver = func.value.id if isinstance(func.value, ast.Name) else None
    if receiver in OS_WRITE_FUNCTIONS and func.attr in OS_WRITE_FUNCTIONS[receiver]:
        return True
    if func.attr in PATH_WRITE_METHODS:
        return True
    if func.attr == "open":
        return _opens_for_writing(call, mode_position=0)
    # `Path.replace(target)` takes exactly one argument; `str.replace(old, new)`
    # takes two. Counting the name alone put every string-munging module in the
    # inventory, which is how this scanner first read 46 modules instead of 34.
    # `dataclasses.replace(obj)` is the one-argument shape that is not a path.
    return (
        func.attr == "replace"
        and receiver not in NON_PATH_REPLACE_RECEIVERS
        and len(call.args) == 1
        and not call.keywords
    )


def _calls_registered_low_level_filesystem_entrypoint(
    tree: ast.AST, relative: str
) -> bool:
    """Whether a registered ctypes filesystem entrypoint is called in ``tree``."""
    entrypoints = LOW_LEVEL_FILESYSTEM_WRITE_ENTRYPOINTS.get(relative, frozenset())
    return bool(entrypoints) and any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in entrypoints
        for node in ast.walk(tree)
    )


PACKAGE_ROOT = Path("loop_apidoc")


def modules_with_file_writes(
    *, package_root: Path = PACKAGE_ROOT, relative_to: Path | None = None
) -> tuple[str, ...]:
    """Every module under `package_root` containing a write call, as sorted
    paths relative to `relative_to` — by default the package's parent, so the
    repository package yields `loop_apidoc/...` regardless of how the root was
    spelled."""
    base = relative_to if relative_to is not None else package_root.parent
    found: list[str] = []
    for path in sorted(package_root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            raise QualityGateFailure(f"cannot parse {path}: {exc}") from exc
        relative = path.relative_to(base).as_posix()
        if (
            _calls_registered_low_level_filesystem_entrypoint(tree, relative)
            or any(
                isinstance(node, ast.Call) and _call_writes(node)
                for node in ast.walk(tree)
            )
        ):
            found.append(relative)
    return tuple(found)


def file_io_registry_gaps(modules: Iterable[str]) -> dict[str, list[str]]:
    """Both directions of drift between the scanned modules and
    `FILE_IO_EXIT_MODULES`: `unregistered` writes without being listed, `stale`
    is listed without writing any more."""
    scanned = set(modules)
    registered = set(FILE_IO_EXIT_MODULES)
    return {
        "unregistered": sorted(scanned - registered),
        "stale": sorted(registered - scanned),
    }


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
    return subprocess.run(cmd, text=True, capture_output=True, timeout=STEP_TIMEOUT_SECONDS)


# typer.rich_utils forces coloured output whenever GITHUB_ACTIONS / FORCE_COLOR /
# PY_COLORS is set, and rich styles an option's leading dashes separately from its name.
# A literal like "--source-quality" is then split across escape sequences, so a signal
# check on raw output passes locally and fails on CI. Compare stripped text instead.
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _excerpt(text: str, limit: int = 4000) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    # Test runners print progress before the useful traceback. Keep both ends
    # so CI-only failures expose the assertion instead of only progress dots.
    head = limit // 2
    tail = limit - head
    return text[:head] + "\n...[truncated]...\n" + text[-tail:]


def required_benchmark_cases() -> tuple[str, ...]:
    return REQUIRED_BENCHMARK_CASES


def required_sanitized_benchmark_cases() -> tuple[str, ...]:
    return SANITIZED_BENCHMARK_CASES


def missing_benchmark_sources(
    *,
    benchmark_root: Path = BENCHMARK_ROOT,
    cases: tuple[str, ...] | list[str] = REQUIRED_BENCHMARK_CASES,
) -> list[str]:
    missing: list[str] = []
    for case in cases:
        src = benchmark_root / case / "sources"
        # rglob so nested layouts (e.g. sources/docs/spec.pdf) count as present;
        # the manifest scanner walks recursively, so the gate must too.
        if not src.is_dir() or not any(path.is_file() for path in src.rglob("*")):
            missing.append(case)
    return missing


# `assemble` requires an audited source package, so the benchmark harness skips a
# case without one. Naming that prerequisite here turns a strict-local skip into a
# precise "generate this package" failure instead of a bare "skips reported".
BENCHMARK_QUALITY_FILES = ("source-quality-report.json", "source-diff.json")


def missing_benchmark_source_quality(
    *,
    benchmark_root: Path = BENCHMARK_ROOT,
    cases: tuple[str, ...] | list[str] = REQUIRED_BENCHMARK_CASES,
) -> list[str]:
    missing: list[str] = []
    for case in cases:
        quality = benchmark_root / case / "source-quality"
        if not all((quality / name).is_file() for name in BENCHMARK_QUALITY_FILES):
            missing.append(case)
    return missing


SOURCE_DERIVATION_DESCRIPTOR = "source-derivation.json"


def required_source_derivation_benchmark_cases() -> tuple[str, ...]:
    return SOURCE_DERIVATION_BENCHMARK_CASES


def _case_relative_path(case_dir: Path, relative: str) -> Path | None:
    """Resolve a descriptor-declared, case-relative path, refusing to escape
    the case directory. Returns None for an absolute path or one containing
    `..`, rather than joining it and trusting the descriptor author."""
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    return case_dir / candidate


def _source_derivation_original_path(benchmark_root: Path, case: str) -> Path | None:
    """The original PDF path a case's descriptor names, or None if the
    descriptor is missing, unreadable, malformed, or points outside the case
    directory. None never means "restored"; callers decide what None means for
    their own check."""
    descriptor_path = benchmark_root / case / SOURCE_DERIVATION_DESCRIPTOR
    try:
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        relative = descriptor["original_document"]["path"]
        if not isinstance(relative, str):
            return None
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
    return _case_relative_path(benchmark_root / case, relative)


def missing_benchmark_source_derivation(
    *,
    benchmark_root: Path = BENCHMARK_ROOT,
    cases: tuple[str, ...] | list[str] = SOURCE_DERIVATION_BENCHMARK_CASES,
) -> list[str]:
    """Cases with a valid `source-derivation.json` whose named original PDF is
    not restored into the case's gitignored `raw/`. A descriptor that is
    missing, unreadable, or malformed is a different failure — reported by
    `invalid_benchmark_source_derivation` instead, so "the PDF is missing" and
    "the descriptor is broken" are never collapsed into the same remedy."""
    missing: list[str] = []
    for case in cases:
        original = _source_derivation_original_path(benchmark_root, case)
        if original is None:
            continue
        if not original.is_file():
            missing.append(case)
    return missing


def invalid_benchmark_source_derivation(
    *,
    benchmark_root: Path = BENCHMARK_ROOT,
    cases: tuple[str, ...] | list[str] = SOURCE_DERIVATION_BENCHMARK_CASES,
) -> list[str]:
    """Cases whose `source-derivation.json` is missing, unreadable, malformed,
    or names an original path outside the case directory."""
    return [
        case
        for case in cases
        if _source_derivation_original_path(benchmark_root, case) is None
    ]


def has_benchmark_skips(stdout: str) -> bool:
    """Detect skipped tests in ``pytest -q`` output.

    Assumes ``pytest -q`` output; not safe for arbitrary text. The reliable path is
    the ``"skipped"`` summary; the progress-dots path is a backup that only matches a
    genuine progress line (dominated by ``.``) to avoid false positives on prose
    words like ``"esp"`` that happen to subset the result-char set.
    """
    if "skipped" in stdout.lower():
        return True
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped or set(stripped) > set(".sfexXpP"):
            continue
        # genuine progress line: an "s" marks a skip, and dots dominate the line
        if "s" in stripped and stripped.count(".") * 2 >= len(stripped):
            return True
    return False


def run_step(name: str, cmd: list[str], *, runner: Runner = _default_runner) -> _RunResult:
    print(f"[quality-gate] {name}: {' '.join(cmd)}")
    try:
        result = runner(cmd)
    except subprocess.TimeoutExpired as exc:
        timeout_val = exc.timeout
        raise QualityGateFailure(
            f"{name} timed out after {timeout_val}s"
        ) from exc
    except OSError as exc:
        raise QualityGateFailure(
            f"{name} could not be started: {exc}"
        ) from exc
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


def _write_source_quality_package(
    root: Path,
    sources: Path,
    *,
    runner: Runner = _default_runner,
) -> Path:
    """Produce assemble's mandatory `--source-quality` package via the real CLI chain.

    `assemble` refuses to build an unaudited run, so every assemble scenario needs
    manifest → inspect-source-risk → assess-sources to have run first. Failures here
    surface as the scenario's own exit code/signal instead of being swallowed.
    """
    manifest = root / "manifest.json"
    risk = root / "source-risk"
    observations = root / "source-quality-observations.json"
    quality = root / "source-quality"
    observations.write_text("[]", encoding="utf-8")
    runner(["uv", "run", "loop-apidoc", "manifest", "--sources", str(sources),
            "--output", str(manifest)])
    runner(["uv", "run", "loop-apidoc", "inspect-source-risk", "--sources", str(sources),
            "--manifest", str(manifest), "--output", str(risk)])
    runner(["uv", "run", "loop-apidoc", "assess-sources", "--sources", str(sources),
            "--manifest", str(manifest), "--source-risk", str(risk),
            "--observations", str(observations), "--source-set", "quality-gate",
            "--output", str(quality)])
    # The path must exist for assemble's option check even when the chain wrote
    # nothing; an empty package still fails assemble loudly, which is the point.
    quality.mkdir(parents=True, exist_ok=True)
    return quality


def run_adversarial_cli_smoke(*, runner: Runner = _default_runner) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    with tempfile.TemporaryDirectory(prefix="loop-apidoc-adv-") as td:
        root = Path(td)

        sources, extraction, out = _write_valid_fixture(root / "normal")
        quality = _write_source_quality_package(root / "normal", sources, runner=runner)
        cmd = ["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
               "--extraction", str(extraction), "--output", str(out),
               "--source-quality", str(quality), "--json"]
        res = runner(cmd)
        signal = res.stdout
        try:
            payload = json.loads(res.stdout)
            signal = f"ok={payload['ok']} status={payload['status']}"
        except json.JSONDecodeError:
            pass
        # cleanup_ok asserts the run dir was created on successful assemble
        # (couples to assemble's run-dir layout by design)
        results.append(ScenarioResult("ADV-001", res.returncode, 0, signal, "ok=True", out.exists()))

        sources, extraction, out = _write_valid_fixture(root / "bad-json")
        quality = _write_source_quality_package(root / "bad-json", sources, runner=runner)
        (extraction / "inventory.json").write_text("{ not json", encoding="utf-8")
        res = runner(["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
                      "--extraction", str(extraction), "--output", str(out),
                      "--source-quality", str(quality), "--json"])
        results.append(ScenarioResult(
            "ADV-002", res.returncode, 2, res.stderr,
            "inventory.json 不是合法 JSON", not out.exists()))

        sources, extraction, out = _write_valid_fixture(root / "localized-keys")
        quality = _write_source_quality_package(root / "localized-keys", sources, runner=runner)
        inventory = dict(BASE_INVENTORY)
        inventory["schemas"] = [{"name": "Bad", "fields": [{"名稱": "id", "型別": "string"}],
                                 "source": "manual.md"}]
        (extraction / "inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
        res = runner(["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
                      "--extraction", str(extraction), "--output", str(out),
                      "--source-quality", str(quality), "--json"])
        results.append(ScenarioResult(
            "ADV-003", res.returncode, 2, res.stderr,
            "schemas[0].fields[0]", not out.exists()))

        sources, extraction, out = _write_valid_fixture(root / "bad-integration")
        quality = _write_source_quality_package(root / "bad-integration", sources, runner=runner)
        (extraction / "integration.json").write_text("[]", encoding="utf-8")
        res = runner(["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
                      "--extraction", str(extraction), "--output", str(out),
                      "--source-quality", str(quality), "--json"])
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
        # Verify the secret bytes did NOT leak into EITHER stream — a regression
        # that surfaces the secret on stderr must still fail the gate.
        secret_absent = "TOP SECRET DO NOT READ" not in f"{res.stdout}\n{res.stderr}"
        results.append(ScenarioResult(
            "ADV-006", res.returncode, 0, signal,
            '"status": "unreadable"', secret_absent))

        # The audited-source prerequisite must be enforced by the CLI itself:
        # a complete, otherwise-valid input set still builds no run directory.
        sources, extraction, out = _write_valid_fixture(root / "no-quality")
        res = runner(["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
                      "--extraction", str(extraction), "--output", str(out), "--json"])
        results.append(ScenarioResult(
            "ADV-007", res.returncode, 2, _strip_ansi(f"{res.stdout}\n{res.stderr}"),
            "--source-quality", not out.exists()))

    return results


def command_plan(
    *,
    strict_local: bool,
    sanitized_fixtures: bool = False,
) -> list[tuple[str, list[str]]]:
    plan: list[tuple[str, list[str]]] = [
        ("ruff", ["uv", "run", "ruff", "check", "."]),
        ("pytest", ["uv", "run", "pytest", "--cov=loop_apidoc"]),
    ]
    if strict_local:
        plan.append(("benchmarks", ["uv", "run", "pytest", "tests/test_benchmarks.py", "-q"]))
    if sanitized_fixtures:
        plan.append((
            "sanitized-fixtures",
            ["uv", "run", "pytest", "tests/test_sanitized_benchmarks.py", "-q"],
        ))
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-local", action="store_true")
    parser.add_argument("--sanitized-fixtures", action="store_true")
    args = parser.parse_args(argv)
    if args.strict_local and args.sanitized_fixtures:
        print(
            "quality-gate error: --strict-local and --sanitized-fixtures cannot be combined",
            file=sys.stderr,
        )
        return 2
    try:
        if args.strict_local:
            missing = missing_benchmark_sources()
            if missing:
                raise QualityGateFailure(
                    "strict-local benchmark sources missing or empty: "
                    + ", ".join(missing)
                )
            unaudited = missing_benchmark_source_quality()
            if unaudited:
                raise QualityGateFailure(
                    "strict-local benchmark source-quality package missing "
                    "(run manifest → inspect-source-risk → assess-sources into "
                    "benchmarks/<case>/source-quality): " + ", ".join(unaudited)
                )
            invalid_descriptors = invalid_benchmark_source_derivation()
            if invalid_descriptors:
                raise QualityGateFailure(
                    "strict-local benchmark source-derivation.json missing, "
                    "unreadable, or malformed: " + ", ".join(invalid_descriptors)
                )
            unrestored = missing_benchmark_source_derivation()
            if unrestored:
                raise QualityGateFailure(
                    "strict-local benchmark source-derivation original PDF missing "
                    "(restore the file named in source-derivation.json into "
                    "benchmarks/<case>/raw): " + ", ".join(unrestored)
                )
        benchmark_result: _RunResult | None = None
        for name, cmd in command_plan(
            strict_local=args.strict_local,
            sanitized_fixtures=args.sanitized_fixtures,
        ):
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
        try:
            scenario_results = run_adversarial_cli_smoke()
        except subprocess.TimeoutExpired as exc:
            raise QualityGateFailure(
                f"adversarial CLI smoke timed out after {exc.timeout}s"
            ) from exc
        except OSError as exc:
            raise QualityGateFailure(
                f"adversarial CLI smoke could not be started: {exc}"
            ) from exc
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
