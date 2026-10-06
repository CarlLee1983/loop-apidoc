# Retire docs/PIPELINE_FOLLOWUPS.md in favour of GitHub issues, and mark specs/handoff.md as legacy

## Goal

Every entry in `docs/PIPELINE_FOLLOWUPS.md` is done or resolved, and the file was last
changed on 2026-08-01. Process documents still send deferred work there:
`docs/CORRECTION_LOOP.md` (lines 35 and 66), `docs/RELEASE_CHECKLIST.md` (line 113), and
`AGENTS.md` (line 439). Delete the file and redirect those documents to GitHub issues
on `CarlLee1983/loop-apidoc`. Git history keeps the resolved entries, and an issue's
open/closed state holds whether the work is still pending.

Separately, `specs/handoff.md` opens with "The lifecycle block is authoritative", and an
agent reading it can mistake ForgeFlow state for current work. Add a notice after its
title saying that it is a legacy record and pointing to the Warrant contract.

## Out of Scope

- The `LAP-*` directories under `specs/stories/`.
- Any change to `specs/handoff.md` other than the inserted notice.
- `docs/RELEASE_NOTES_*.md`, and the text of other Story files.
- Rewriting `docs/DEVELOPMENT_OPPORTUNITIES_2026-07-24.md`; only its one citation of
  `PIPELINE_FOLLOWUPS.md` changes.
- Creating GitHub issues, labels, or issue templates.
- Any other `AGENTS.md` section.

## Acceptance Criteria

1. `git ls-files docs/PIPELINE_FOLLOWUPS.md` prints nothing.
2. `git grep -n 'PIPELINE_FOLLOWUPS' -- ':!specs/stories/*.md'` prints only the
   `docs/DEVELOPMENT_OPPORTUNITIES_2026-07-24.md` citation, and that citation's link
   target is
   `https://github.com/CarlLee1983/loop-apidoc/blob/001c8a1/docs/PIPELINE_FOLLOWUPS.md`.
3. In `docs/CORRECTION_LOOP.md` step 3, the bullet for larger work and the
   `## Failure Record Template` sentence both name a GitHub issue as the place to record
   it. Neither names `docs/PIPELINE_FOLLOWUPS.md`.
4. The `docs/RELEASE_CHECKLIST.md` invariant-check bullet accepts "a GitHub issue"
   where it named `docs/PIPELINE_FOLLOWUPS.md`, and its other alternatives are unchanged.
5. The `AGENTS.md` `## Further docs` line for pipeline follow-ups now points to GitHub
   issues on `CarlLee1983/loop-apidoc`.
6. `diff <(git show 001c8a1:AGENTS.md) AGENTS.md` shows changes to that one line only.
7. `specs/handoff.md` line 1 is still `# ForgeFlow Handoff`. Immediately after it, a
   notice says that the file is a legacy ForgeFlow record, that its lifecycle block is
   not current state, and that the contract is the `## Warrant` section of `AGENTS.md`.
   `diff <(git show 001c8a1:specs/handoff.md) specs/handoff.md | grep '^<'` prints
   nothing.
8. `git diff --name-status main...HEAD` lists only `M AGENTS.md`,
   `M docs/CORRECTION_LOOP.md`, `M docs/RELEASE_CHECKLIST.md`,
   `M docs/DEVELOPMENT_OPPORTUNITIES_2026-07-24.md`, `D docs/PIPELINE_FOLLOWUPS.md`,
   `M specs/handoff.md`, and this Story file
   (`specs/stories/retire-pipeline-followups-and-mark-handoff-legacy.md`).
9. `make verify` exits 0.
