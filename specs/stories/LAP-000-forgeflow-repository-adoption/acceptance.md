# Acceptance Criteria

## Happy Path

* [x] AC-001: `specs/.forgeflow-adoption` records ForgeFlow version `0.3.2` and revision `7bbdf443ead484780e23df9abf055095d4c629e2`.
* [x] AC-002: The repository-local Story Development Skill and all three Story templates are byte-identical to ForgeFlow v0.3.2.
* [x] AC-003: ForgeFlow `story-check`, `handoff-check`, and Doctor accept the adopted Story, lifecycle, and static repository contract.
* [x] AC-004: CI installs Node and Python dependencies, then runs one explicitly named `Canonical verification` step using `make verify`.

## Business Rules

* [x] AC-005: `make verify` runs `npm run tag:check`, `npm run docs:check`, and `uv run python scripts/quality_gate.py` without installing dependencies or mutating release state.
* [x] AC-006: Existing `AGENTS.md` architecture, source authority, evidence, fail-closed, and TDD rules remain intact and gain the required ForgeFlow Story lifecycle guidance.
* [x] AC-007: The quality gate retains repository hygiene, ruff, full pytest with the 92.5% coverage floor, benchmark discovery/skip semantics, and seven-scenario adversarial CLI smoke.
* [x] AC-008: `make verify` is the single local and CI completion contract; duplicated direct CI gate steps are removed.

## Failure Cases

* [x] AC-009: Make stops and exits nonzero when any tag, documentation, or Python quality-gate command fails.
* [x] AC-010: Missing private benchmark sources may skip source-backed cases in the default public-CI-safe gate, while discovery still runs and skips are never called source-backed PASS.

## Regression Requirements

* [x] AC-011: No LAP-000 change appears under `loop_apidoc/`; CLI and package behavior are unchanged.
* [x] AC-012: Coverage remains 92.5%; no tests, hygiene checks, ruff checks, adversarial smoke, or benchmark requirements are removed or weakened.
* [x] AC-013: No dependency upgrade, version bump, release, tag, push, merge, publication, branch protection, ruleset, Pages, or ForgeFlowV2 change occurs.
* [x] AC-014: Final `make verify` exits 0.

## Verification Notes

Environment setup: `npm ci` and `uv sync --dev`. Run ForgeFlow v0.3.2
`scripts/story-check specs/stories/LAP-000-forgeflow-repository-adoption`,
`scripts/handoff-check specs/handoff.md`, and `scripts/doctor .` using documented
syntax. Finish with `make verify`; compare its three commands, results, duration,
coverage, and benchmark skips with the recorded pre-adoption baseline.
