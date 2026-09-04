# Acceptance Criteria

## Happy Path

* [x] AC-001: LAP-002 passes the ForgeFlow v0.3.5 `story-check`.
* [x] AC-002: `specs/.forgeflow-adoption` records version `0.3.5` and revision
  `9ac8eb3b08ab41733afb96c2d9e6258d0421b370` exactly.
* [x] AC-003: All three local Story templates are byte-identical to ForgeFlow
  v0.3.5.
* [x] AC-004: The repository-local Story Development Skill is byte-identical to
  ForgeFlow v0.3.5.
* [x] AC-012: Review Preparation reports the Story and acceptance mapping,
  design decisions, test evidence, assumptions, risks, and suggested Human
  Review areas.

## Business Rules

* [x] AC-005: `AGENTS.md` retains all loop-apidoc rules and adds Review
  Preparation, Classification truthfulness, verification freshness, REVIEW
  feedback loops, SPEC_BLOCKED, Code Quality automation boundaries, and
  human-only DONE guidance.
* [x] AC-006: LAP-000, LAP-001, and LAP-002 all pass the ForgeFlow v0.3.5
  `story-check`.
* [x] AC-007: ForgeFlow v0.3.5 `handoff-check` reports
  `HANDOFF_CONTRACT_OK`.
* [x] AC-008: ForgeFlow v0.3.5 Doctor reports no contract drift.
* [x] AC-009: CI continues to use only `make verify` as canonical verification.

## Failure Cases

* [x] AC-011: The final `make verify` exits 0; any failing constituent check
  remains a failure and is not bypassed, removed, or weakened.

## Regression Requirements

* [x] AC-010: Product code, dependencies, the 92.5% coverage floor, Makefile/CI
  verification contract, and existing quality gates remain unchanged.

## Verification Notes

Using the ForgeFlow v0.3.5 checkout at revision
`9ac8eb3b08ab41733afb96c2d9e6258d0421b370`, run:

```sh
scripts/story-check \
  specs/stories/LAP-000-forgeflow-repository-adoption \
  specs/stories/LAP-001-source-backed-benchmark-attestation \
  specs/stories/LAP-002-forgeflow-0-3-5-adoption-upgrade
scripts/handoff-check specs/handoff.md
scripts/doctor .
make verify
```

After the final handoff update, run `make verify` and `handoff-check` again.
PASS places LAP-002 in REVIEW only; a human must accept it before DONE.
