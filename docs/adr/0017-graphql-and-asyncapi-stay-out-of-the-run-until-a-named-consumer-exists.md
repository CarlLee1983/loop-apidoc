---
status: accepted
---

# GraphQL and AsyncAPI stay out of the run until a named consumer exists

The Core already has a protocol/transport seam and deterministic GraphQL SDL and AsyncAPI 3
projection compilers. Regression tests pin both compilers against a GitHub public GraphQL
schema and a pinned OGC AsyncAPI conformance example. Wiring them into the public run would
take little code.

It is deliberately not done. This record transcribes the sequencing decision revised on
2026-07-30 in `docs/PRODUCT_EXTENSION_ROADMAP.md`
(`## Defer protocol main-flow integration until preceding blockers are resolved`).
`docs/PROTOCOL_EXPANSION_DESIGN.md` carries the same freeze in its status line.

The reason is that the fixtures establish format-level testability, not product demand or
an end-to-end grounding contract. The product invariant is that a source is the only
authority for a factual claim. A protocol path without a real supplier source set has no
way to show that its output is grounded, and without a downstream consumer it has no
acceptance criteria to fail against. Integrating anyway would put a path into the run that
nothing can show to be right or wrong.

## Decision

No CLI command, run artifact, validation, diff/score, or Foundry path for GraphQL/AsyncAPI is
added until this ADR records a named downstream consumer and its acceptance contract. The
compilers and their regression tests stay as they are.

## Considered options

- **Integrate behind an opt-in flag.** An opt-in flag still ships an ungrounded path, and
  an operator who opts in has no acceptance contract that would tell them the output is
  wrong.
- **Delete the compilers until demand appears.** Deleting the compilers would discard a
  seam that is already tested and cheap to keep. Keeping it is what makes the later
  integration a bounded vertical slice rather than a redesign.

## Consequences

To resume, the consumer and its acceptance contract are added to this record, or a
superseding ADR is written, before any implementation starts.

**Falsified if:** a GraphQL or AsyncAPI path reaches the run without a named consumer.
Concretely, this decision no longer holds when `loop_apidoc/cli.py` exposes a command or
option that runs the GraphQL or AsyncAPI compilers in `loop_apidoc/domain/projections.py`,
or when a run artifact, validation, diff/score, or Foundry module calls those compilers,
while this record still names no consumer.
