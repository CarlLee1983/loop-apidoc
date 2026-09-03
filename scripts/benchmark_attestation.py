"""Per-case, machine-readable benchmark evidence attestation.

`make verify` says whether the repository passed. It does not say, case by case,
*which* assurance level each benchmark case actually reached — and the four
harness layers plus the two supplemental lanes are exactly the kind of
distinction that gets flattened into "the benchmarks pass" when the only record
is pytest's human output. This module writes that record down in one versioned,
strict document so a committed, discovered, skipped, sanitized, or
expected-failure case can never be paraphrased into a source-backed PASS.

It owns no inventory and no evidence definition of its own. The required cases,
the sanitized lane, the source-derivation lane, the exact-evidence-parity lane
and every prerequisite predicate come from `scripts/quality_gate.py`; what
actually executed comes from one pytest run's JUnit XML, never from parsing
pytest's prose. Three test names below are the only binding between an assurance
level and the check that establishes it, and `tests/test_benchmark_attestation.py`
fails loudly if one of them is renamed rather than letting the report silently
downgrade to "nothing was established".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loop_apidoc import __version__ as LOOP_APIDOC_VERSION  # noqa: E402
from loop_apidoc.privacy import find_sensitive_value  # noqa: E402
from loop_apidoc.url_safety import redact_text, redact_url  # noqa: E402
from scripts.quality_gate import (  # noqa: E402
    BENCHMARK_QUALITY_FILES,
    BENCHMARK_ROOT,
    SOURCE_DERIVATION_DESCRIPTOR,
    required_benchmark_cases,
    required_exact_evidence_parity_benchmark_cases,
    required_sanitized_benchmark_cases,
    required_source_derivation_benchmark_cases,
)

SCHEMA_VERSION = "benchmark-attestation/v1"
MODES = ("ci-safe", "strict-local")

#: The one binding between an assurance level and the check that establishes it.
#: Deliberately three names and no more: everything else the report says is
#: derived from a reviewed inventory or a file predicate that already exists.
BENCHMARK_TEST_MODULE = "tests.test_benchmarks"
SANITIZED_TEST_MODULE = "tests.test_sanitized_benchmarks"
SOURCE_BACKED_PRIMARY_TEST = "test_benchmark_case"
EXACT_EVIDENCE_PARITY_TEST = "test_case_obeys_declared_core_parity_contract"
SANITIZED_EXACT_EVIDENCE_TEST = (
    "test_sanitized_fixture_proves_fixture_backed_exact_evidence_parity"
)

HARNESS_TEST_TARGETS = (
    "tests/test_benchmarks.py",
    "tests/test_sanitized_benchmarks.py",
)

COMMITTED_IDENTITY_FILES = (
    "extraction/inventory.json",
    "expected/validation.expect.json",
)
CORE_PARITY_FILE = "expected/core-parity.json"
SANITIZED_DESCRIPTOR = "sanitized-fixture.json"

CONTRACT_VERSIONS = {
    "core_parity": 1,
    "sanitized_fixture": 1,
    "source_derivation": 1,
}

REDACTED = "[REDACTED]"


class AttestationError(RuntimeError):
    """A fail-closed condition: no attestation is produced."""


# --- inputs ----------------------------------------------------------------


@dataclass(frozen=True)
class Binding:
    """What a report is true *of*. A report without this is unattributable."""

    repository_commit: str
    repository_dirty: bool
    loop_apidoc_version: str


@dataclass(frozen=True)
class HarnessOutcome:
    """One JUnit `testcase`, reduced to what an assurance claim needs."""

    module: str
    test: str
    case_id: str | None
    outcome: str  # passed | skipped | failed
    message: str


def _read_json(path: Path, label: str) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AttestationError(f"{label} is missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AttestationError(f"{label} is unreadable or malformed") from exc
    if not isinstance(document, dict):
        raise AttestationError(f"{label} is not a JSON object")
    return document


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_junit(xml_text: str) -> tuple[HarnessOutcome, ...]:
    """Machine-readable outcomes from one pytest run.

    JUnit XML rather than pytest's prose: a summary line is a rendering choice
    that can change between versions, while this element shape is a contract
    pytest publishes. A `testcase` is attributed to a benchmark case only by its
    parametrization id, so the mapping is exact rather than a name heuristic.
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise AttestationError("pytest JUnit report is malformed") from exc

    outcomes: list[HarnessOutcome] = []
    for element in root.iter("testcase"):
        name = element.get("name", "")
        outcome = "passed"
        message = ""
        for state, label in (("failure", "failed"), ("error", "failed"), ("skipped", "skipped")):
            child = element.find(state)
            if child is not None:
                outcome = label
                message = child.get("message", "")
                break
        outcomes.append(
            HarnessOutcome(
                module=element.get("classname", "").split("::")[0],
                test=name.split("[", 1)[0],
                case_id=name[name.find("[") + 1 : -1] if name.endswith("]") else None,
                outcome=outcome,
                message=message,
            )
        )
    return tuple(outcomes)


# --- redaction -------------------------------------------------------------


def redact_report_text(text: str) -> str:
    """Make one externally-derived string safe to persist.

    Three separate leaks, so three separate steps: a URL query credential
    (`redact_text`), an absolute filesystem path — every pytest skip message
    carries one — and a bare credential-shaped value such as a JWT that belongs
    to no URL at all. The last check is deliberately whole-string and blunt: a
    report is governance evidence, and a coarse `[REDACTED]` costs a reader far
    less than a leaked token costs everyone.
    """
    redacted = redact_text(text)
    redacted = " ".join(
        REDACTED if token.startswith("/") and len(token) > 1 else token
        for token in redacted.split(" ")
    )
    if find_sensitive_value(redacted) is not None:
        return REDACTED
    return redacted


def redact_reference_url(url: str) -> str:
    return redact_url(url)


# --- per-case assembly -----------------------------------------------------


@dataclass(frozen=True)
class _Asset:
    path: str
    kind: str
    required: bool
    available: bool


def _directory_has_file(path: Path) -> bool:
    return path.is_dir() and any(item.is_file() for item in path.rglob("*"))


def _case_relative(case_dir: Path, declared: str, label: str) -> Path:
    candidate = Path(declared)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise AttestationError(f"{label} declares a path outside the case directory")
    return case_dir / candidate


def _validate_committed_contracts(case_dir: Path, case_id: str) -> dict:
    """Every committed declaration a report reads, checked before it is read.

    Returns the case's expected validation contract. A malformed core-parity
    declaration fails here rather than being reported as an absent expectation:
    an attestation that survives a broken contract is worth nothing.
    """
    for relative in COMMITTED_IDENTITY_FILES:
        _read_json(case_dir / relative, f"{case_id}: {relative}")

    expected = _read_json(
        case_dir / COMMITTED_IDENTITY_FILES[1], f"{case_id}: {COMMITTED_IDENTITY_FILES[1]}"
    )
    status = expected.get("current_status")
    if status not in {"PASS", "FAIL"}:
        raise AttestationError(
            f"{case_id}: expected/validation.expect.json declares an unusable "
            f"current_status"
        )

    parity = _read_json(case_dir / CORE_PARITY_FILE, f"{case_id}: {CORE_PARITY_FILE}")
    if parity.get("schema_version") != CONTRACT_VERSIONS["core_parity"]:
        raise AttestationError(
            f"{case_id}: expected/core-parity.json is not schema_version "
            f"{CONTRACT_VERSIONS['core_parity']}"
        )
    if parity.get("expected_legacy_status") != status:
        raise AttestationError(
            f"{case_id}: expected/core-parity.json contradicts "
            f"expected/validation.expect.json"
        )
    return expected


def _sanitized_reference(case_dir: Path, case_id: str) -> dict:
    """The sanitized lane descriptor, checked for staleness before it is trusted.

    The committed sanitized subset is the one source artifact this repository
    *does* redistribute, so its recorded digest is checkable here and a drifted
    or tampered file is a fail-closed condition rather than a footnote.
    """
    descriptor = _read_json(case_dir / SANITIZED_DESCRIPTOR, f"{case_id}: {SANITIZED_DESCRIPTOR}")
    if descriptor.get("schema_version") != CONTRACT_VERSIONS["sanitized_fixture"]:
        raise AttestationError(f"{case_id}: {SANITIZED_DESCRIPTOR} is not schema_version 1")
    if descriptor.get("case_id") != case_id:
        raise AttestationError(f"{case_id}: {SANITIZED_DESCRIPTOR} names another case")
    if descriptor.get("strict_local_eligible") is not False:
        raise AttestationError(
            f"{case_id}: {SANITIZED_DESCRIPTOR} must declare strict_local_eligible false"
        )
    sanitized = descriptor.get("sanitized_source") or {}
    path = _case_relative(case_dir, str(sanitized.get("path", "")), f"{case_id}: {SANITIZED_DESCRIPTOR}")
    if not path.is_file():
        raise AttestationError(f"{case_id}: sanitized source named by the descriptor is missing")
    if _digest(path) != sanitized.get("sha256"):
        raise AttestationError(
            f"{case_id}: sanitized source digest does not match {SANITIZED_DESCRIPTOR}"
        )
    original = descriptor.get("original_snapshot") or {}
    return {
        "kind": "sanitized_fixture",
        "path": str(sanitized.get("path")),
        "url": redact_reference_url(str(original.get("source_url", ""))),
        "digest": str(sanitized.get("sha256")),
    }


def _derivation_reference(case_dir: Path, case_id: str) -> dict:
    """The PDF source-derivation descriptor, with the one digest that is tracked.

    Neither the original PDF nor the derived Markdown is committed, so the
    descriptor's `derived_markdown.sha256` is the only anchor. Where the local
    Markdown exists it is checked: a stale or tampered local copy must fail the
    attestation, not quietly back a source-backed claim.
    """
    descriptor = _read_json(
        case_dir / SOURCE_DERIVATION_DESCRIPTOR, f"{case_id}: {SOURCE_DERIVATION_DESCRIPTOR}"
    )
    if descriptor.get("schema_version") != CONTRACT_VERSIONS["source_derivation"]:
        raise AttestationError(
            f"{case_id}: {SOURCE_DERIVATION_DESCRIPTOR} is not schema_version 1"
        )
    if descriptor.get("case_id") != case_id:
        raise AttestationError(f"{case_id}: {SOURCE_DERIVATION_DESCRIPTOR} names another case")
    original = descriptor.get("original_document") or {}
    derived = descriptor.get("derived_markdown") or {}
    label = f"{case_id}: {SOURCE_DERIVATION_DESCRIPTOR}"
    original_path = _case_relative(case_dir, str(original.get("path", "")), label)
    derived_path = _case_relative(case_dir, str(derived.get("path", "")), label)
    if derived_path.is_file() and _digest(derived_path) != derived.get("sha256"):
        raise AttestationError(
            f"{case_id}: derived Markdown digest does not match "
            f"{SOURCE_DERIVATION_DESCRIPTOR}"
        )
    return {
        "kind": "source_derivation",
        "path": str(derived.get("path")),
        "url": redact_reference_url(str(original.get("source_url", ""))),
        "digest": str(derived.get("sha256")),
        "_original_path": original_path,
        "_original_relative": str(original.get("path")),
    }


def _case_assets(
    case_dir: Path,
    *,
    sanitized: dict | None,
    derivation: dict | None,
) -> tuple[_Asset, ...]:
    assets = [
        _Asset(relative, "committed", True, (case_dir / relative).is_file())
        for relative in (*COMMITTED_IDENTITY_FILES, CORE_PARITY_FILE)
    ]
    assets.append(
        _Asset("sources/", "operator", True, _directory_has_file(case_dir / "sources"))
    )
    assets.append(
        _Asset(
            "source-quality/",
            "operator",
            True,
            all((case_dir / "source-quality" / name).is_file() for name in BENCHMARK_QUALITY_FILES),
        )
    )
    if sanitized is not None:
        assets.append(_Asset(SANITIZED_DESCRIPTOR, "committed", True, True))
        assets.append(_Asset(sanitized["path"], "committed", True, True))
    if derivation is not None:
        assets.append(_Asset(SOURCE_DERIVATION_DESCRIPTOR, "committed", True, True))
        assets.append(
            _Asset(
                derivation["_original_relative"],
                "operator",
                True,
                derivation["_original_path"].is_file(),
            )
        )
    return tuple(assets)


def _case_outcomes(
    outcomes: Iterable[HarnessOutcome], case_id: str, module: str
) -> tuple[HarnessOutcome, ...]:
    return tuple(
        outcome
        for outcome in outcomes
        if outcome.case_id == case_id and outcome.module == module
    )


def _named_outcome(outcomes: Iterable[HarnessOutcome], test: str) -> HarnessOutcome | None:
    return next((outcome for outcome in outcomes if outcome.test == test), None)


def _build_case(
    *,
    case_id: str,
    benchmark_root: Path,
    mode: str,
    outcomes: Sequence[HarnessOutcome],
) -> dict:
    case_dir = benchmark_root / case_id
    expected = _validate_committed_contracts(case_dir, case_id)

    sanitized = (
        _sanitized_reference(case_dir, case_id)
        if case_id in required_sanitized_benchmark_cases()
        else None
    )
    derivation = (
        _derivation_reference(case_dir, case_id)
        if case_id in required_source_derivation_benchmark_cases()
        else None
    )
    assets = _case_assets(case_dir, sanitized=sanitized, derivation=derivation)
    unavailable = sorted(asset.path for asset in assets if asset.required and not asset.available)

    benchmark_outcomes = _case_outcomes(outcomes, case_id, BENCHMARK_TEST_MODULE)
    sanitized_outcomes = _case_outcomes(outcomes, case_id, SANITIZED_TEST_MODULE)

    primary = _named_outcome(benchmark_outcomes, SOURCE_BACKED_PRIMARY_TEST)
    parity = _named_outcome(benchmark_outcomes, EXACT_EVIDENCE_PARITY_TEST)
    sanitized_parity = _named_outcome(sanitized_outcomes, SANITIZED_EXACT_EVIDENCE_TEST)

    source_backed_executed = primary is not None and primary.outcome == "passed"
    sanitized_executed = (
        sanitized_parity is not None and sanitized_parity.outcome == "passed"
    )

    # R8: parity is a replay *result*, never a `core-parity.json` expectation.
    if parity is not None and parity.outcome == "passed":
        exact_evidence_parity = "source_backed_replay"
    elif sanitized_executed:
        exact_evidence_parity = "sanitized_fixture_replay"
    else:
        exact_evidence_parity = "not_established"

    declared_status = expected["current_status"]
    classification = "PASS" if declared_status == "PASS" else "EXPECTED_FAIL"

    all_outcomes = (*benchmark_outcomes, *sanitized_outcomes)
    failed = [outcome for outcome in all_outcomes if outcome.outcome == "failed"]
    skipped = [outcome for outcome in all_outcomes if outcome.outcome == "skipped"]

    strict_local_eligible = not unavailable
    strict_local_passed = (
        mode == "strict-local"
        and strict_local_eligible
        and source_backed_executed
        and not failed
        and not skipped
    )

    reasons = _reasons(
        unavailable=unavailable,
        source_backed_executed=source_backed_executed,
        sanitized_executed=sanitized_executed,
        exact_evidence_parity=exact_evidence_parity,
        skipped=bool(skipped),
        failed=bool(failed),
        strict_local_passed=strict_local_passed,
    )

    return {
        "case_id": case_id,
        "lanes": {
            "required": True,
            "sanitized_fixture": sanitized is not None,
            "source_derivation": derivation is not None,
            "exact_evidence_parity": case_id
            in required_exact_evidence_parity_benchmark_cases(),
        },
        "assets": [
            {
                "path": asset.path,
                "kind": asset.kind,
                "required": asset.required,
                "available": asset.available,
            }
            for asset in assets
        ],
        "unavailable_prerequisites": unavailable,
        "source_reference": _public_reference(sanitized or derivation),
        "assurance": {
            "committed": True,
            "discovered": True,
            "prerequisites_available": not unavailable,
            "source_backed_executed": source_backed_executed,
            "sanitized_fixture_executed": sanitized_executed,
            "exact_evidence_parity": exact_evidence_parity,
            "strict_local_eligible": strict_local_eligible,
            "strict_local_passed": strict_local_passed,
        },
        "harness": {
            "expectation": classification,
            # Tri-state on purpose. `false` must mean the harness contradicted
            # its expectation; a case whose source-backed assertions never ran
            # has established nothing either way, and reporting that as `false`
            # reads as a violation that did not happen (R3, R4).
            "conformant": _conformance(primary, failed),
            "executed": sum(1 for o in all_outcomes if o.outcome == "passed"),
            "skipped": len(skipped),
            "failed": len(failed),
            "failures": [
                {
                    "test": outcome.test,
                    "message": redact_report_text(outcome.message),
                }
                for outcome in sorted(failed, key=lambda item: (item.module, item.test))
            ],
        },
        "contract_validation": {
            "declared_status": declared_status,
            "harness_classification": classification,
            "observed_status": declared_status if source_backed_executed else None,
        },
        "reasons": reasons,
    }


def _conformance(
    primary: HarnessOutcome | None, failed: Sequence[HarnessOutcome]
) -> bool | None:
    if failed:
        return False
    if primary is not None and primary.outcome == "passed":
        return True
    return None


def _public_reference(reference: dict | None) -> dict | None:
    if reference is None:
        return None
    return {
        "kind": reference["kind"],
        "path": reference["path"],
        "url": reference["url"],
        "digest": reference["digest"],
    }


def _reasons(
    *,
    unavailable: Sequence[str],
    source_backed_executed: bool,
    sanitized_executed: bool,
    exact_evidence_parity: str,
    skipped: bool,
    failed: bool,
    strict_local_passed: bool,
) -> list[str]:
    """Stable reason codes, sorted. Prose would be a second vocabulary; these
    are the terms `docs/BENCHMARK_VALIDATION_PLAN.md` already defines."""
    reasons = {"committed-fixture-present", "discovered-by-harness"}
    if unavailable:
        reasons.add("prerequisites-unavailable")
    if skipped:
        reasons.add("source-backed-assertions-skipped")
    if failed:
        reasons.add("harness-check-failed")
    if source_backed_executed:
        reasons.add("source-backed-execution-passed")
    else:
        reasons.add("source-backed-execution-not-established")
    if sanitized_executed:
        reasons.add("sanitized-fixture-replay-passed")
    if exact_evidence_parity == "not_established":
        reasons.add("exact-evidence-parity-not-replayed")
    else:
        reasons.add(f"exact-evidence-parity-{exact_evidence_parity.replace('_', '-')}")
    if strict_local_passed:
        reasons.add("strict-local-passed")
    return sorted(reasons)


def build_attestation(
    *,
    benchmark_root: Path,
    mode: str,
    binding: Binding,
    outcomes: Sequence[HarnessOutcome],
    subprocess_exit_code: int | None = None,
) -> dict:
    """The whole report. Pure over its inputs, so the same revision, assets and
    execution results always render the same document (R11)."""
    if mode not in MODES:
        raise AttestationError(f"unknown execution mode: {mode}")

    cases = required_benchmark_cases()
    committed = {
        directory.name
        for directory in sorted(benchmark_root.iterdir())
        if all((directory / relative).is_file() for relative in COMMITTED_IDENTITY_FILES)
    }
    if committed != set(cases):
        raise AttestationError(
            "committed benchmark fixtures do not match REQUIRED_BENCHMARK_CASES: "
            + ", ".join(sorted(committed.symmetric_difference(cases)))
        )

    reported = [
        _build_case(
            case_id=case_id, benchmark_root=benchmark_root, mode=mode, outcomes=outcomes
        )
        for case_id in sorted(cases)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "binding": {
            "repository_commit": binding.repository_commit,
            "repository_dirty": binding.repository_dirty,
            "loop_apidoc_version": binding.loop_apidoc_version,
            "execution_mode": mode,
            "contract_versions": dict(CONTRACT_VERSIONS),
        },
        "execution": {
            "harness_targets": list(HARNESS_TEST_TARGETS),
            "subprocess_exit_code": subprocess_exit_code,
        },
        "totals": {
            "required_cases": len(reported),
            "prerequisites_available": sum(
                1 for case in reported if case["assurance"]["prerequisites_available"]
            ),
            "source_backed_executed": sum(
                1 for case in reported if case["assurance"]["source_backed_executed"]
            ),
            "sanitized_fixture_executed": sum(
                1 for case in reported if case["assurance"]["sanitized_fixture_executed"]
            ),
            "exact_evidence_parity_established": sum(
                1
                for case in reported
                if case["assurance"]["exact_evidence_parity"] != "not_established"
            ),
            "strict_local_passed": sum(
                1 for case in reported if case["assurance"]["strict_local_passed"]
            ),
        },
        "cases": reported,
    }


# --- schema ----------------------------------------------------------------


def _object(properties: dict, required: Sequence[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


ATTESTATION_SCHEMA = _object(
    {
        "schema_version": {"const": SCHEMA_VERSION},
        "binding": _object(
            {
                "repository_commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                "repository_dirty": {"type": "boolean"},
                "loop_apidoc_version": {"type": "string", "minLength": 1},
                "execution_mode": {"enum": list(MODES)},
                "contract_versions": _object(
                    {name: {"type": "integer"} for name in CONTRACT_VERSIONS},
                    sorted(CONTRACT_VERSIONS),
                ),
            },
            (
                "repository_commit",
                "repository_dirty",
                "loop_apidoc_version",
                "execution_mode",
                "contract_versions",
            ),
        ),
        "execution": _object(
            {
                "harness_targets": {"type": "array", "items": {"type": "string"}},
                "subprocess_exit_code": {"type": ["integer", "null"]},
            },
            ("harness_targets", "subprocess_exit_code"),
        ),
        "totals": _object(
            {
                name: {"type": "integer", "minimum": 0}
                for name in (
                    "required_cases",
                    "prerequisites_available",
                    "source_backed_executed",
                    "sanitized_fixture_executed",
                    "exact_evidence_parity_established",
                    "strict_local_passed",
                )
            },
            (
                "required_cases",
                "prerequisites_available",
                "source_backed_executed",
                "sanitized_fixture_executed",
                "exact_evidence_parity_established",
                "strict_local_passed",
            ),
        ),
        "cases": {
            "type": "array",
            "minItems": 1,
            "items": _object(
                {
                    "case_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
                    "lanes": _object(
                        {
                            name: {"type": "boolean"}
                            for name in (
                                "required",
                                "sanitized_fixture",
                                "source_derivation",
                                "exact_evidence_parity",
                            )
                        },
                        (
                            "required",
                            "sanitized_fixture",
                            "source_derivation",
                            "exact_evidence_parity",
                        ),
                    ),
                    "assets": {
                        "type": "array",
                        "items": _object(
                            {
                                "path": {"type": "string", "pattern": "^[^/].*$"},
                                "kind": {"enum": ["committed", "operator"]},
                                "required": {"type": "boolean"},
                                "available": {"type": "boolean"},
                            },
                            ("path", "kind", "required", "available"),
                        ),
                    },
                    "unavailable_prerequisites": {
                        "type": "array",
                        "items": {"type": "string", "pattern": "^[^/].*$"},
                    },
                    "source_reference": {
                        "oneOf": [
                            {"type": "null"},
                            _object(
                                {
                                    "kind": {
                                        "enum": ["sanitized_fixture", "source_derivation"]
                                    },
                                    "path": {"type": "string", "pattern": "^[^/].*$"},
                                    "url": {"type": "string"},
                                    "digest": {
                                        "type": "string",
                                        "pattern": "^[0-9a-f]{64}$",
                                    },
                                },
                                ("kind", "path", "url", "digest"),
                            ),
                        ]
                    },
                    "assurance": _object(
                        {
                            "committed": {"type": "boolean"},
                            "discovered": {"type": "boolean"},
                            "prerequisites_available": {"type": "boolean"},
                            "source_backed_executed": {"type": "boolean"},
                            "sanitized_fixture_executed": {"type": "boolean"},
                            "exact_evidence_parity": {
                                "enum": [
                                    "not_established",
                                    "sanitized_fixture_replay",
                                    "source_backed_replay",
                                ]
                            },
                            "strict_local_eligible": {"type": "boolean"},
                            "strict_local_passed": {"type": "boolean"},
                        },
                        (
                            "committed",
                            "discovered",
                            "prerequisites_available",
                            "source_backed_executed",
                            "sanitized_fixture_executed",
                            "exact_evidence_parity",
                            "strict_local_eligible",
                            "strict_local_passed",
                        ),
                    ),
                    "harness": _object(
                        {
                            "expectation": {"enum": ["PASS", "EXPECTED_FAIL"]},
                            "conformant": {"type": ["boolean", "null"]},
                            "executed": {"type": "integer", "minimum": 0},
                            "skipped": {"type": "integer", "minimum": 0},
                            "failed": {"type": "integer", "minimum": 0},
                            "failures": {
                                "type": "array",
                                "items": _object(
                                    {
                                        "test": {"type": "string"},
                                        "message": {"type": "string"},
                                    },
                                    ("test", "message"),
                                ),
                            },
                        },
                        (
                            "expectation",
                            "conformant",
                            "executed",
                            "skipped",
                            "failed",
                            "failures",
                        ),
                    ),
                    "contract_validation": _object(
                        {
                            "declared_status": {"enum": ["PASS", "FAIL"]},
                            "harness_classification": {"enum": ["PASS", "EXPECTED_FAIL"]},
                            "observed_status": {"enum": ["PASS", "FAIL", None]},
                        },
                        ("declared_status", "harness_classification", "observed_status"),
                    ),
                    "reasons": {
                        "type": "array",
                        "items": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
                    },
                },
                (
                    "case_id",
                    "lanes",
                    "assets",
                    "unavailable_prerequisites",
                    "source_reference",
                    "assurance",
                    "harness",
                    "contract_validation",
                    "reasons",
                ),
            ),
        },
    },
    ("schema_version", "binding", "execution", "totals", "cases"),
)


def validate_report(report: dict) -> None:
    """Strict, versioned, and fail-closed on an unknown field: a reader that
    trusts this document must be able to trust that nothing undeclared rode
    along inside it."""
    errors = sorted(
        Draft202012Validator(ATTESTATION_SCHEMA).iter_errors(report),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        raise AttestationError(
            "attestation does not satisfy "
            f"{SCHEMA_VERSION}: {errors[0].json_path}: {errors[0].message}"
        )


# --- rendering -------------------------------------------------------------


def _tick(value: bool) -> str:
    return "yes" if value else "no"


def _conformance_label(value: bool | None) -> str:
    if value is None:
        return "not established"
    return "yes" if value else "no"


def render_markdown(report: dict) -> str:
    """The same statements as the JSON, for a person. Every status and reason is
    read back out of the report rather than recomputed, so the two renderings
    cannot disagree (AC-010)."""
    binding = report["binding"]
    lines = [
        "# Benchmark Attestation",
        "",
        f"* Contract: `{report['schema_version']}`",
        f"* Repository commit: `{binding['repository_commit']}`"
        + (" (dirty worktree)" if binding["repository_dirty"] else ""),
        f"* loop-apidoc version: `{binding['loop_apidoc_version']}`",
        f"* Execution mode: `{binding['execution_mode']}`",
        "* Contract versions: "
        + ", ".join(
            f"`{name}` v{value}" for name, value in sorted(binding["contract_versions"].items())
        ),
        "",
        "A skip is not a pass, and a sanitized-fixture replay is neither a full",
        "source-backed pass nor a strict-local pass.",
        "",
        "## Cases",
        "",
        "| Case | Harness expectation | Contract validation | Source-backed | "
        "Sanitized fixture | Exact-evidence parity | Strict-local | "
        "Unavailable prerequisites |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in report["cases"]:
        assurance = case["assurance"]
        validation = case["contract_validation"]
        lines.append(
            "| `{case_id}` | {expectation} (conformant: {conformant}) | "
            "{classification} / declared `{declared}` / observed {observed} | "
            "{source_backed} | {sanitized} | {parity} | {strict} | {missing} |".format(
                case_id=case["case_id"],
                expectation=case["harness"]["expectation"],
                conformant=_conformance_label(case["harness"]["conformant"]),
                classification=validation["harness_classification"],
                declared=validation["declared_status"],
                observed=(
                    f"`{validation['observed_status']}`"
                    if validation["observed_status"]
                    else "not executed"
                ),
                source_backed=_tick(assurance["source_backed_executed"]),
                sanitized=_tick(assurance["sanitized_fixture_executed"]),
                parity=assurance["exact_evidence_parity"],
                strict=_tick(assurance["strict_local_passed"]),
                missing=", ".join(f"`{path}`" for path in case["unavailable_prerequisites"])
                or "none",
            )
        )
    lines.extend(["", "## Reasons", ""])
    for case in report["cases"]:
        lines.append(
            f"* `{case['case_id']}`: "
            + ", ".join(f"`{reason}`" for reason in case["reasons"])
        )
        for failure in case["harness"]["failures"]:
            lines.append(f"  * failed `{failure['test']}`: {failure['message']}")
    references = [case for case in report["cases"] if case["source_reference"]]
    if references:
        lines.extend(["", "## Source references", ""])
        for case in references:
            reference = case["source_reference"]
            lines.append(
                f"* `{case['case_id']}` ({reference['kind']}): `{reference['path']}` "
                f"sha256 `{reference['digest']}` from {reference['url']}"
            )
    lines.append("")
    return "\n".join(lines)


# --- output ----------------------------------------------------------------


def write_exclusive(path: Path, text: str) -> None:
    """Create the output file or refuse.

    `O_EXCL | O_NOFOLLOW` rather than a `Path.exists()` check: the question is
    not whether a file was there a moment ago but whether *this* call created
    the exact file it names, so a symlink, a pre-existing report, and a race all
    land on the same refusal. The content is complete before this is called, so
    a refusal leaves nothing behind to mistake for a result (AC-014).
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise AttestationError(f"refusing to overwrite an existing output path: {path.name}") from exc
    except OSError as exc:
        raise AttestationError(f"output path is unusable: {path.name}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)


# --- execution -------------------------------------------------------------


def repository_binding(*, root: Path) -> Binding:
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        raise AttestationError("repository commit is unavailable; cannot bind the attestation")
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    return Binding(
        repository_commit=commit.stdout.strip(),
        repository_dirty=bool(status.stdout.strip()),
        loop_apidoc_version=LOOP_APIDOC_VERSION,
    )


def run_harness(*, root: Path) -> tuple[tuple[HarnessOutcome, ...], int]:
    """One pytest run over both harness modules, read back as JUnit XML."""
    with tempfile.TemporaryDirectory() as workspace:
        report_path = Path(workspace) / "harness.xml"
        completed = subprocess.run(
            [
                "uv",
                "run",
                "pytest",
                *HARNESS_TEST_TARGETS,
                "-q",
                "-p",
                "no:cacheprovider",
                f"--junitxml={report_path}",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if not report_path.is_file():
            raise AttestationError(
                "pytest produced no JUnit report; the harness run could not be read"
            )
        return parse_junit(report_path.read_text(encoding="utf-8")), completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a per-case benchmark attestation.")
    parser.add_argument("--mode", choices=MODES, default="ci-safe")
    parser.add_argument("--benchmark-root", default=str(BENCHMARK_ROOT))
    parser.add_argument("--json-out")
    parser.add_argument("--markdown-out")
    args = parser.parse_args(argv)

    if not args.json_out and not args.markdown_out:
        print(
            "benchmark-attestation error: at least one of --json-out or "
            "--markdown-out is required",
            file=sys.stderr,
        )
        return 2

    root = Path(__file__).resolve().parents[1]
    try:
        binding = repository_binding(root=root)
        outcomes, exit_code = run_harness(root=root)
        report = build_attestation(
            benchmark_root=Path(args.benchmark_root),
            mode=args.mode,
            binding=binding,
            outcomes=outcomes,
            subprocess_exit_code=exit_code,
        )
        if args.mode == "strict-local":
            blocked = [
                case["case_id"] for case in report["cases"] if case["unavailable_prerequisites"]
            ]
            if blocked:
                raise AttestationError(
                    "strict-local attestation requires every prerequisite: "
                    + ", ".join(blocked)
                )
        validate_report(report)
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        markdown = render_markdown(report)
        if args.json_out:
            write_exclusive(Path(args.json_out), rendered)
        if args.markdown_out:
            write_exclusive(Path(args.markdown_out), markdown)
    except AttestationError as exc:
        print(f"benchmark-attestation FAILED\n{exc}", file=sys.stderr)
        return 1
    print(
        f"[benchmark-attestation] {report['totals']['required_cases']} required cases, "
        f"{report['totals']['source_backed_executed']} source-backed executed, "
        f"{report['totals']['strict_local_passed']} strict-local passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
