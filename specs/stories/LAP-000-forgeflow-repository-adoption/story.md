# Story: LAP-000 ForgeFlow Repository Adoption

## Goal

Establish the first verifiable ForgeFlow repository-governance baseline for
loop-apidoc without changing product behavior or weakening existing quality gates.

## Context

loop-apidoc already has mature source-grounding, test, documentation, release,
and quality-gate rules. ForgeFlow v0.3.2 adds a Story lifecycle and one canonical
repository completion command around those existing controls.

## Classification

* Security sensitive: no
* Baseline conformance: yes

## Scope

### In Scope

* Record ForgeFlow v0.3.2 revision `7bbdf443ead484780e23df9abf055095d4c629e2`.
* Install the v0.3.2 Story templates and repository-local Story Development Skill.
* Define LAP-000, the Story lifecycle handoff, `make verify`, and matching CI use.
* Preserve and include the existing tag, documentation, and Python quality gates.

### Out of Scope

* Product code, CLI/package behavior, Core/legacy/shadow/strict behavior, or API-format features.
* Source-backed benchmark attestation or benchmark contract changes.
* Dependency upgrades, version bumps, release metadata, publication, GitHub settings, Pages, or unrelated cleanup.

## Inputs

* The approved LAP-000 prompt and loop-apidoc repository baseline `7ec38049944dfc5f9f738a23ee6ed72875fe890f`.
* ForgeFlow v0.3.2 at revision `7bbdf443ead484780e23df9abf055095d4c629e2`.
* Existing `npm run tag:check`, `npm run docs:check`, and `uv run python scripts/quality_gate.py` gates.

## Outputs

* ForgeFlow adoption marker, Story templates, local Skill, Story README, LAP-000 Story, and handoff.
* Root `Makefile` exposing `make verify` and CI invoking that command after dependency setup.
* Verification evidence comparing the pre-adoption gates with the canonical post-adoption gate.

## Rules

* R1: `make verify` is the only canonical repository-level completion gate.
* R2: It runs tag policy, documentation consistency, and the existing Python quality gate non-interactively and propagates failures.
* R3: Existing source authority, evidence, fail-closed, TDD, 92.5% coverage, repository hygiene, ruff, full pytest, adversarial smoke, and benchmark skip semantics remain unchanged.
* R4: Dependency installation remains explicit environment setup and is not part of `make verify`.
* R5: ForgeFlow PASS permits human review only; it never authorizes approval, merge, release, tag, push, or publish.

## Expected Errors

* Missing dependencies or a failing tag, docs, hygiene, ruff, pytest, coverage, or smoke check makes `make verify` exit nonzero.
* Missing local private benchmark sources remain accurately reported as skips in public-CI-safe mode; they are not reported as source-backed PASS.
* An invalid Story, handoff, or repository structure is rejected by the corresponding ForgeFlow checker.

## Dependencies

* Existing Node and uv dependency setup: `npm ci` and `uv sync --dev`.
* Existing loop-apidoc quality tooling and a ForgeFlow v0.3.2 checkout for contract checks.

## Constraints

* Preserve the existing `AGENTS.md`; append only the minimum ForgeFlow guidance.
* Do not modify `loop_apidoc/`, product tests, dependency declarations/locks, benchmark contracts, Pages workflow, or ForgeFlowV2.
* Do not install dependencies from `make verify` or perform release/external mutations.

## Superseded Behavior

* `tests/test_plugin_manifest.py::test_docsentry_document_governance_is_configured_and_runs_in_ci` and `.github/workflows/ci.yml` currently require/execute the docs check directly in CI alongside direct tag and Python quality-gate steps. After adoption, the test follows the complete CI → `make verify` → docs-check chain and `make verify` becomes the sole canonical completion gate invoked by CI; the actual checks, ordering, exit failures, coverage floor, discovery guard, benchmark skip semantics, and adversarial smoke behavior are not weakened or reinterpreted.
