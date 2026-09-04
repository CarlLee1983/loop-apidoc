# Story: LAP-002 ForgeFlow 0.3.5 Adoption Upgrade

## Goal

Upgrade loop-apidoc's ForgeFlow adoption snapshot from v0.3.2 to the released
v0.3.5 contract while preserving product behavior, quality gates, and the
canonical CI verification contract.

## Context

The current adoption marker and repository-local Story Development Skill record
ForgeFlow v0.3.2. That version covers implementation, `make verify`, and handoff
reporting, but does not fully define Review Preparation, Classification
truthfulness, verification freshness, review feedback loops, or the boundary
between automated Code Quality checks and Human Review judgments.

## Classification

* Security sensitive: no
* Baseline conformance: yes

## Scope

### In Scope

* Record ForgeFlow v0.3.5 revision
  `9ac8eb3b08ab41733afb96c2d9e6258d0421b370`.
* Upgrade the three managed Story templates with the v0.3.5 bootstrap flow.
* Update the repository-local Story Development Skill to the v0.3.5 version.
* Integrate v0.3.5 Review Preparation, Classification truthfulness,
  verification freshness, Code Quality, and Human Review guidance into the
  repository-owned `AGENTS.md` without replacing loop-apidoc rules.
* Define LAP-002 and update the lifecycle handoff for Human Review.
* Verify LAP-000, LAP-001, LAP-002, the handoff, repository contract, and the
  complete current implementation with the v0.3.5 checks and `make verify`.

### Out of Scope

* Changes under `loop_apidoc/` or to public CLI, OpenAPI, GraphQL, or AsyncAPI
  behavior.
* Python, Node, or other dependency upgrades.
* Changes to the 92.5% coverage floor or removal, weakening, or replacement of
  tag, documentation, ruff, pytest, benchmark, or adversarial checks.
* Makefile or CI changes unless an existing contract defect is demonstrated.
* Merge, push, tag, release, publication, or changes to ForgeFlowV2.

## Inputs

* The approved LAP-002 request and loop-apidoc baseline
  `f6dbb0994a2a389a065ede431dc2771a9bb37499`.
* ForgeFlow v0.3.5 at revision
  `9ac8eb3b08ab41733afb96c2d9e6258d0421b370`.
* Existing loop-apidoc Story, handoff, `AGENTS.md`, CI, and `make verify`
  contracts.

## Outputs

* Updated ForgeFlow adoption marker, Story templates, local Story Development
  Skill, repository guidance, LAP-002 Story, and handoff.
* Review Preparation evidence mapping the Story and acceptance criteria to the
  actual changes and verification results.

## Rules

* R1: Supplier-source authority, source grounding, TDD, security, and existing
  quality rules remain unchanged.
* R2: `make verify` remains the only canonical repository and CI completion
  gate; v0.3.5 checks supplement but do not replace it.
* R3: Classification must describe the actual change and verification evidence
  must cover the current implementation.
* R4: A behavior-affecting change after PASS requires another complete
  `make verify`; a final handoff-only change must be explicitly attributed.
* R5: A changes-requested review returns to IMPLEMENTING and requires a fresh
  full PASS before REVIEW; missing or changed requirements move to SPEC_BLOCKED
  for human revision and approval.
* R6: Only a human may accept REVIEW and advance the Story to DONE.

## Expected Errors

* A marker, template, or local Skill that differs from v0.3.5 fails the exact
  comparison or Doctor check.
* An incomplete Story or lifecycle handoff fails the corresponding v0.3.5
  static contract check.
* Any existing tag, documentation, repository hygiene, ruff, pytest, coverage,
  benchmark, or adversarial failure makes `make verify` fail.
* A PASS that predates a behavior-affecting change is stale and cannot support
  REVIEW until `make verify` passes again.

## Dependencies

* A clean ForgeFlow v0.3.5 checkout at the specified revision.
* Existing Node and uv development dependencies and loop-apidoc verification
  tooling.

## Constraints

* Preserve the complete repository-owned `AGENTS.md`; manually integrate only
  the new v0.3.5 guidance.
* Use the v0.3.5 bootstrap `--upgrade --dry-run` before the actual upgrade.
* Do not introduce alternate verification entry points or external mutations.

## Superseded Behavior

* `specs/.forgeflow-adoption` — replace the v0.3.2 version and revision with the
  released v0.3.5 snapshot identity.
* `skills/story-development/SKILL.md` — extend the v0.3.2 implementation and
  delivery workflow with v0.3.5 Review Preparation, Classification truthfulness,
  verification freshness, and REVIEW feedback states.
* `AGENTS.md` ForgeFlow Story Development guidance — extend the v0.3.2 flow with
  v0.3.5 Review Preparation, Code Quality responsibility boundaries, fresh PASS
  requirements, REVIEW feedback loops, SPEC_BLOCKED, and human-only DONE.
