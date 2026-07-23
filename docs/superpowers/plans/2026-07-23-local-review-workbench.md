# Local Review Workbench Implementation Plan

> **For implementation:** execute in order. Keep the workbench local and
> provider-independent; never add model invocation or contract mutation.

## 1. Establish review models and Foundry persistence

1. Add `loop_apidoc/review/models.py` for the review request, binding, snapshot,
   item disposition, handoff task, decision, review state, and explicit review
   errors.
2. Add deterministic digest/subject-ID helpers in a pure review module. Digest
   only completed-run artifacts that `diff.loader.load_run_artifacts` accepts;
   do not treat a run ID as its identity.
3. Extend `loop_apidoc/foundry/paths.py` with the candidate decision path.
4. Extend `loop_apidoc/foundry/store.py` with the sole read/write functions for
   review decisions. Reject malformed persisted JSON loudly.
5. Extend Foundry models with compatible `ReviewSummary` defaults and optional
   asset `approved_by`; add review artifact metadata so downstream callers can
   locate the approved decision.
6. Update `approve_candidate` to copy decision metadata, derive/persist review
   summary and preserve `known_gaps`; it must still leave `current.json`
   unchanged when promotion fails.
7. Start with model/store/approval tests for legacy model loading and clean/
   follow-up approval states.

## 2. Build the review workflow seam

1. Add `loop_apidoc/review/workflow.py` with `open_review`, `save_decision`, and
   `approve_review`.
2. `open_review` must validate a new run before import. If the candidate already
   exists, reuse it only when canonical artifact digests match; never pass
   `overwrite=True`.
3. Resolve an existing current asset and compare its copied `artifacts/` with
   the candidate through `load_run_artifacts` plus `build_diff_report` in
   memory. A missing current is baseline mode; corrupt current data is an error.
4. Validate decision subject IDs and ensure every stored decision has the exact
   binding returned by the current snapshot.
5. On approval, recompute the binding, write the decision before promotion, and
   derive unresolved handoff/known-gap state. Call Foundry with soft validation
   override only when required; never make validation or diff findings disappear.
6. Add seam-level tests for import, reopen, collision, baseline, comparison,
   stale candidate/base, invalid decision, soft approval, and immutable
   candidate contract artifacts.

## 3. Add the loopback GUI adapter and CLI command

1. Add `loop_apidoc/review/web.py` using `http.server` plus bundled static
   HTML/JavaScript/CSS in the review package. Bind only `127.0.0.1`.
2. Provide fixed snapshot, decision, approval, and fixed-artifact routes. Use a
   generated session token for every write and reject arbitrary paths.
3. Add `review` to root `loop_apidoc/cli.py` with `--project`, `--docset`,
   `--run`, `--port`, and `--no-open`; it opens a review workflow then starts the
   adapter. Browser-launch failure must print the URL and keep serving.
4. Add adapter tests for loopback route behavior, session authorization,
   invalid JSON, stale decision conflicts, and path traversal rejection. Do not
   use a browser or external network in tests.

## 4. Update user and agent documentation

1. Update `README.en.md` and `README.md` with the review command, candidate to
   current flow, local-only scope, soft approval, and `needs_follow_up` signal.
2. Update `docs/onboarding*.html`, `docs/operator-manual*.html`,
   `docs/architecture-manual*.html`, `docs/introduction*.html`, and
   `docs/index*.html` wherever command lists, lifecycle diagrams, or Foundry
   descriptions would otherwise be inaccurate.
3. Update `AGENTS.md` and `CLAUDE.md` consistently: add the review package,
   local server adapter, write exits, artifact layout, and current review state.
4. Update `skills/loop-apidoc/SKILL.md` only with the post-assembly review and
   handoff path; retain source grounding, no automatic approval, and provider
   independence.

## 5. Verify and inspect

1. Run focused review, Foundry, diff, CLI, and documentation tests.
2. Run `uv run ruff check .` and the full `uv run pytest` suite; address any
   changed test count explicitly.
3. Exercise `uv run loop-apidoc review --help` and relevant Foundry help.
4. Scan authored Markdown for unresolved placeholders/contradictions, check
   links, run `git diff --check`, and inspect `git status --short` without
   adding the pre-existing release-plan file.
