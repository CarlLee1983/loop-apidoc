# Story: LAP-001 Source-Backed Benchmark Attestation

## Goal

Give an API contract maintainer one reproducible, per-case evidence report that
states the strongest assurance level each required benchmark case actually
reached, so a committed, discovered, skipped, sanitized, or expected-failure
case is never reported as a source-backed PASS.

## Context

`make verify` is the only repository-level completion gate, and the benchmark
harness already separates committed fixtures, discovery, source-backed
execution, and strict-local preflight, plus the supplemental sanitized-fixture
and PDF source-derivation lanes. What is missing is a machine-readable,
per-case statement of which of those levels each case reached in one concrete
run. Today the evidence exists only as pytest's human output plus prose in
`docs/BENCHMARK_VALIDATION_PLAN.md`, which is exactly the shape that lets a
skip be paraphrased as a pass.

This is repository governance evidence. It adds no document parser, no API
protocol capability, and no public `loop-apidoc` CLI command.

## Classification

* Security sensitive: yes
* Baseline conformance: no

## Scope

### In Scope

* Add the repository-level, non-interactive `scripts/benchmark_attestation.py` seam.
* Define the versioned `benchmark-attestation/v1` structured contract.
* Report every required benchmark case exactly once, from the existing reviewed inventory.
* Report each case's required assets and their availability.
* Distinguish committed, discovered, prerequisites unavailable, source-backed executed, sanitized-fixture executed, exact-evidence parity, and strict-local eligible/passed.
* Report harness expectation conformance separately from the API contract validation status.
* Bind the report to the repository revision, `loop-apidoc` version, execution mode, and applicable contract versions.
* Fail closed on malformed, missing, stale, tampered, or mutually contradictory inputs.
* Emit both JSON and Markdown to caller-provided output paths.
* Add behavior, failure-case, and security regression tests.
* Update the English and Traditional-Chinese documentation for this capability.
* Update `specs/handoff.md`.

### Out of Scope

* Restoring or downloading missing supplier historical documents.
* Passing a newer, synthetic, sanitized, or error-page document off as an original source.
* Changing benchmark extraction or expected results to obtain a PASS.
* Adding PDF, DOCX, GitBook, HTML, or any other parsing capability.
* GraphQL or AsyncAPI mainline integration.
* Core production graduation or changing the default architecture mode.
* Automatic Foundry import, approval, merge, release, tag, push, or publish.
* Modifying the ForgeFlowV2 repository.
* Dependency upgrades, version releases, or unrelated refactoring.

## Inputs

* `scripts/quality_gate.py::REQUIRED_BENCHMARK_CASES` and the sanitized, source-derivation, and exact-evidence-parity lane inventories.
* Each case's committed `extraction/inventory.json`, `expected/validation.expect.json`, and `expected/core-parity.json`.
* Each case's optional committed `sanitized-fixture.json` and `source-derivation.json` descriptors.
* Operator-provided, gitignored `benchmarks/<case>/sources/`, `source-quality/`, and `raw/` assets.
* The JUnit XML result of one `pytest` run over `tests/test_benchmarks.py` and `tests/test_sanitized_benchmarks.py`.
* Caller-provided `--json-out` and `--markdown-out` paths, `--mode`, and `--benchmark-root`.

## Outputs

* A `benchmark-attestation/v1` JSON document validated against a strict, versioned schema.
* A Markdown report carrying the same per-case status and reasons as the JSON.
* A non-zero exit and no output file on any fail-closed condition.

## Rules

* R1: `REQUIRED_BENCHMARK_CASES` is the single source of truth for the required case inventory.
* R2: Every required case appears exactly once in the report.
* R3: File presence proves only that an asset exists; it never proves a check ran or passed.
* R4: Only a check that actually executed and produced a successful result is marked passed.
* R5: A skip is never a pass.
* R6: Sanitized-fixture assurance is reported separately from full source-backed and strict-local assurance.
* R7: An EXPECTED_FAIL case may be marked harness conformant when its result matches expectation, and its contract validation status still stays `FAIL`.
* R8: Exact-evidence parity is established only by an actual exact-evidence replay result, never inferred from `core-parity.json` expectations.
* R9: A missing `sources/`, `source-quality/`, or required original source is listed as an explicit unavailable prerequisite.
* R10: The attestation never persists supplier source content, source excerpts, credentials, unredacted URLs, or local absolute paths.
* R11: The same repository revision, input assets, and execution results produce a semantically identical, stably ordered report.
* R12: The benchmark inventory, evidence-tier definitions, and core validation logic are reused, never duplicated.
* R13: The capability never approves, publishes, or rewrites any Normative or Effective Contract.
* R14: `make verify` remains the only repository completion contract.

## Expected Errors

* A required case whose committed identity files are missing, unreadable, or malformed fails the run.
* A committed fixture set that does not exactly match `REQUIRED_BENCHMARK_CASES` fails the run.
* A `core-parity.json`, `sanitized-fixture.json`, or `source-derivation.json` that is missing, malformed, stale, or tampered fails the run.
* A `validation.expect.json` whose `current_status` is neither `PASS` nor `FAIL` fails the run.
* An output path that exists, is a symlink, or cannot be created exclusively fails the run before any bytes are written.
* A rendered report that does not validate against the strict schema fails the run and is not persisted.
* `--mode strict-local` with any unavailable prerequisite fails the run.

## Dependencies

* Existing `scripts/quality_gate.py` inventories and prerequisite helpers.
* Existing `loop_apidoc.url_safety` and `loop_apidoc.privacy` redaction primitives.
* `jsonschema`, already a declared runtime dependency.
* `pytest` JUnit XML, already available through the dev dependency group.

## Constraints

* No new public `loop-apidoc` CLI command and no change to `loop_apidoc/` public behavior.
* No parsing of pytest human-readable text; machine-readable JUnit XML only.
* Existing CI-safe, strict-local, sanitized-fixture, 92.5% coverage, and skip semantics are not weakened.
* The seam is non-interactive and callable identically from CI and a local shell.

## Trust Boundary Fields

* `case.case_id` — the reviewed inventory entry in `scripts/quality_gate.py`
* `case.assets[].path` — a case-relative asset name resolved under `--benchmark-root`
* `case.source_reference.url` — the official URL declared in `sanitized-fixture.json` or `source-derivation.json`
* `case.source_reference.digest` — the SHA-256 declared in those descriptors
* `case.harness.failures[].test` — a JUnit `testcase` name produced by the pytest subprocess
* `case.harness.failures[].message` — a JUnit failure or skip message produced by the pytest subprocess
* `run.subprocess_exit_code` — the pytest subprocess exit status
* `subprocess.stderr` — the pytest subprocess standard error stream
* `--json-out` — the caller-provided JSON output path
* `--markdown-out` — the caller-provided Markdown output path
* `--benchmark-root` — the caller-provided benchmark root directory
