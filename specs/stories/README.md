# Stories

This repository follows Warrant; the contract lives in the `## Warrant` section
of `AGENTS.md`.

A Story is a single file at `specs/stories/<slug>.md` with exactly three
sections: Goal, Out of Scope, and Acceptance Criteria. It carries no status,
owner, priority, or lifecycle field.

A Story is approved only when a human commits it to the default branch or
explicitly assigns it in the current session. A Story an agent drafted or
committed itself is not approved.

Completion is proven by `make verify`, with every acceptance criterion mapped
to a reproducible observation.

The `LAP-*` directories under `specs/stories/` and `specs/handoff.md` are
legacy records from an earlier protocol, not pending work.
