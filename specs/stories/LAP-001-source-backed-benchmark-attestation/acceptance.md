# Acceptance Criteria

## Happy Path

* [x] AC-001: `story.md` and `acceptance.md` satisfy the ForgeFlow v0.3.2 Story contract and `scripts/story-check` reports PASS.
* [x] AC-002: The attestation contains every required benchmark case, each exactly once.
* [x] AC-003: Adding or removing a required case changes the attestation inventory with no second hand-maintained list.
* [x] AC-012: The report binds the repository commit, `loop-apidoc` version, execution mode, and the applicable contract versions.

## Business Rules

* [x] AC-004: A case missing its source or audit package is reported as prerequisite unavailable and never as a source-backed PASS.
* [x] AC-005: A sanitized-fixture result is never marked as full source-backed or strict-local PASS.
* [x] AC-006: Only a case whose exact-evidence replay actually completed is marked with exact-evidence parity.
* [x] AC-007: An EXPECTED_FAIL case reports both harness expectation matched and contract validation `FAIL`.
* [x] AC-010: Markdown and JSON present the same status and the same reasons for every case.
* [x] AC-011: Case ordering and reason ordering are deterministic.

## Failure Cases

* [x] AC-008: A malformed, stale, or tampered source, source-quality audit, derivation descriptor, or expected contract makes the command exit non-zero with no successful attestation.
* [x] AC-009: The JSON validates against an explicit, versioned, strict schema in which an unknown field fails closed.
* [x] AC-014: An output error leaves no partial report that could be mistaken for a success.

## Regression Requirements

* [x] AC-013: Output carries no supplier source content, unredacted credential URL, local absolute path, or sensitive subprocess output.
* [x] AC-015: Existing CI-safe, strict-local, sanitized-fixtures, 92.5% coverage, and skip semantics are unchanged.
* [x] AC-016: Final `make verify` exits 0.

## Security Fixture Matrix

| Source field | Payload | Expected result | Persisted locations | Verification |
| --- | --- | --- | --- | --- |
| `case.source_reference.url` | `https://example.test/spec.pdf?X-Amz-Signature=6f1c2a9b4d8e0f3a5c7b9d1e2f4a6c8b` | redact | `cases[].source_reference.url` | `tests/test_benchmark_attestation.py::test_credential_bearing_source_url_is_redacted_in_both_outputs` |
| `case.assets[].path` | `/private/tmp/bench-root/newebpay-mpg/sources/spec.md` | omit | `cases[].assets[].path` | `tests/test_benchmark_attestation.py::test_report_never_persists_an_absolute_path` |
| `case.harness.failures[].message` | `AssertionError: token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.7Hk3QpX9sVfLm2Nq0RtYwZbCdEfGhIjKlMnOpQrStUv` | redact | `cases[].harness.failures[].message` | `tests/test_benchmark_attestation.py::test_credential_shaped_subprocess_output_is_redacted` |
| `benchmarks/<case>/sources/spec.md` | `MerchantSecretKey=8f4c1b0a9d6e3f27` | omit | `cases[].assets[].path` | `tests/test_benchmark_attestation.py::test_supplier_source_content_never_reaches_the_report` |
| `case.case_id` | `newebpay-mpg` | preserve | `cases[].case_id` | `tests/test_benchmark_attestation.py::test_case_identity_relative_asset_and_digest_are_preserved` |
| `--json-out` | `/private/tmp/attestation-out/report.json` | reject | `out/benchmark-attestation.json` | `tests/test_benchmark_attestation.py::test_symlinked_or_existing_output_path_is_rejected_without_partial_output` |

## Verification Notes

Environment setup is `npm ci` and `uv sync --dev`. Run ForgeFlow v0.3.2
`scripts/story-check specs/stories/LAP-001-source-backed-benchmark-attestation`
and `scripts/handoff-check specs/handoff.md` from the repository root, then the
focused module `uv run pytest tests/test_benchmark_attestation.py -q`, and
finish with `make verify`.

The attestation seam is:

```bash
uv run python scripts/benchmark_attestation.py \
  --mode ci-safe \
  --json-out out/benchmark-attestation.json \
  --markdown-out out/benchmark-attestation.md
```

On a machine without the private supplier snapshots every case is expected to
report `prerequisites unavailable`; that is the correct result and must never be
described as a source-backed PASS.
