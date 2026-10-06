# Give docs/ARCHITECTURE.md a decision boundary list derived from the ADRs

## Goal

The fifteen ADRs under `docs/adr/` each close with a `**Falsified if:**` paragraph, and
the paths that paragraph names in backticks are the files the decision depends on. At
commit `165516d`, `docs/ARCHITECTURE.md` links to none of them, and ADR 0002's
falsification paragraph names no path at all, so a change to a guarded file does not
bring its decision back into view. Add a boundary list to `docs/ARCHITECTURE.md` with
one row per ADR, give ADR 0002 concrete path markers, and add a test that keeps the list
in step with `docs/adr/`. After that, adding an ADR or changing its guarded paths
without updating the architecture document fails `make verify`.

## Out of Scope

- The text of ADRs 0001 and 0003-0015.
- In ADR 0002, any change other than the `**Falsified if:**` paragraph; the decision
  itself and its existing conditions stay as written.
- Writing new ADRs, or changing an ADR's `status`.
- Existing `docs/ARCHITECTURE.md` text; the section is only added.
- `AGENTS.md`, `scripts/quality_gate.py`, and the HTML manuals.

## Acceptance Criteria

1. `grep -c '^## 決策邊界' docs/ARCHITECTURE.md` prints `1`.
2. In this Story, a **guarded path** of an ADR is a backtick span inside its
   `**Falsified if:**` paragraph for which `Path(span).exists()` is true when run from
   the repository root, with a trailing `/` allowed for directories.
3. The `## 決策邊界` section has exactly one row per file matching `docs/adr/[0-9]*.md`.
   Each row links to that file with a relative `adr/<filename>` link and lists exactly
   that ADR's guarded paths, each in backticks.
4. ADR 0002's `**Falsified if:**` paragraph names `loop_apidoc/domain/conformance.py`,
   `loop_apidoc/core/conformance.py`, and `loop_apidoc/feedback/` in backticks. Each of
   its existing conditions remains present.
5. `tests/docs/test_adr_boundary_list.py` exists and checks criteria 1-3 by reading
   `docs/adr/` and `docs/ARCHITECTURE.md`. `uv run pytest tests/docs/test_adr_boundary_list.py`
   passes, and the test fails with a message naming the ADR after any one row is
   deleted from `docs/ARCHITECTURE.md`. Show that failure in the completion report,
   then restore the row.
6. `for f in docs/adr/0001* docs/adr/00{03..15}*; do git diff --quiet 165516d -- "$f" || echo "$f"; done`
   prints nothing.
7. `git diff --name-status main...HEAD` lists only `M docs/ARCHITECTURE.md`,
   `M docs/adr/0002-separate-documentary-and-empirical-authority.md`,
   `A tests/docs/test_adr_boundary_list.py`, and this Story file
   (`specs/stories/architecture-adr-boundary-list.md`).
8. `make verify` exits 0.
