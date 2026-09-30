# Migrate from the ForgeFlow protocol to Warrant

## Goal

Replace this repository's ForgeFlow Story protocol with Warrant, so that agents
find one contract in `AGENTS.md`: Stories are single files at
`specs/stories/<slug>.md`, approval is a human commit, and completion is proven
by `make verify`.

* In `AGENTS.md`, replace the ForgeFlow sections (currently lines 5-54:
  `## ForgeFlow Story Development`, `### Review Preparation`, and the closing
  REVIEW/DONE paragraph) with the Warrant block from
  `/Users/carl/Dev/Carl/Warrant/plugin/skills/warrant/agents-block.md`, its
  verification-command placeholder replaced by `make verify`.
* Keep the protocol-neutral `### Code Quality` bullets (currently lines 45-50)
  under a `## Code Quality` heading. The TDD guidance
  (`## Development workflow: test-driven development`, currently line 91) and
  everything from `## What this is` onward stay as they are.
* Delete `specs/.forgeflow-adoption`, `specs/stories/_template/` (all three
  files), and `.agents/skills/story-development/SKILL.md`.
* Rewrite `specs/stories/README.md` for Warrant.

## Out of Scope

* `specs/handoff.md` and the directory-style Stories
  `specs/stories/LAP-000-forgeflow-repository-adoption/`,
  `specs/stories/LAP-001-source-backed-benchmark-attestation/`, and
  `specs/stories/LAP-002-forgeflow-0-3-5-adoption-upgrade/`: they stay
  byte-identical as legacy history.
* The product's "handoff" feature (provider erratum handoff, the `handoff/`
  pack, review `decision.json` handoff) in `loop_apidoc/`, `tests/`, `README.md`,
  `README.en.md`, and `docs/`.
* The `verify` target in `Makefile`, and `.github/workflows/`.
* Any `AGENTS.md` section other than the ForgeFlow block being replaced.
* Dependency changes, version bumps, releases, tags, pushes, or merges.

## Acceptance Criteria

1. `grep -n -E '[Ff]orge[Ff]low|story-development|Review Preparation|\bIMPLEMENTING\b|SPEC_BLOCKED' AGENTS.md`
   prints nothing.
2. The text of `agents-block.md`, with its verification-command placeholder
   replaced by `make verify`, appears verbatim in `AGENTS.md`, and no
   placeholder text from that block remains in `AGENTS.md`.
3. `AGENTS.md` has a `## Code Quality` section whose bullets are byte-identical
   to lines 45-50 of `AGENTS.md` on `main` at the time of approval.
4. `diff <(git show main:AGENTS.md | sed -n '/^## What this is/,$p') <(sed -n '/^## What this is/,$p' AGENTS.md)`
   prints nothing.
5. `git ls-files specs/.forgeflow-adoption specs/stories/_template .agents/skills/story-development`
   prints nothing.
6. `specs/stories/README.md` states that a Story is `specs/stories/<slug>.md`
   with exactly the sections Goal, Out of Scope, and Acceptance Criteria; that
   a Story is approved only when a human commits it to the default branch or
   assigns it explicitly; that completion is proven by `make verify`; and that
   the `LAP-*` directories and `specs/handoff.md` are legacy records, not
   pending work.
7. `grep -n -i -E 'forgeflow|_template|story-check|story-development|task\.md' specs/stories/README.md`
   prints nothing.
8. `git grep -n -E 'story-development|forgeflow-adoption|stories/_template' -- ':!specs/stories/LAP-*' ':!specs/handoff.md' ':!specs/stories/warrant-migration.md'`
   prints nothing.
9. `git diff --name-status main...HEAD` lists only: `M AGENTS.md`,
   `M specs/stories/README.md`, `D specs/.forgeflow-adoption`, `D` for the three
   `specs/stories/_template/` files, `D .agents/skills/story-development/SKILL.md`,
   and this Story file if it is not already on `main`.
10. `make verify` exits 0.
