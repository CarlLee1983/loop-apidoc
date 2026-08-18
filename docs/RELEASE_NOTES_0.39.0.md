# loop-apidoc 0.39.0 release notes

Release date: 2026-08-18

## Summary

Lists that live in the code, prose that is checked against them, and two more formats refused by name

## Changed

0.38.0 worked on what a source may leak into the pipeline. This release works on a
different failure: a claim written in prose that nothing verifies. Several of the repo's
inventories existed twice — once as a Python list the code reads, once as a sentence a
person maintains — and every one of those pairs was kept in step by hand. The pattern in
each change below is the same: the machine-readable list stays the truth, the document
stays the human-readable presentation, and a test binds them so a silent drift fails.

- **`.txt` and `.csv` are refused by name.** Both were falling through to the generic
  unknown-format branch, which reports that the pipeline does not recognise the file —
  true of the format, false about the content, and useless to the operator holding one.
  They now join `.doc` and the spreadsheet formats as recognised-but-unsupported, each
  with the operator-side conversion that resolves it, in both report languages. No
  converter is planned for any of the four; ADR 0012 was extended rather than reopened.
- **Every acquisition path is graded on one scale.** Which commands have carried a real
  supplier source end to end was documented per-command in prose that nobody could check.
  A controlled list in `scripts/quality_gate.py` now grades each registered command, and
  the four grading tables (both READMEs, both operator manuals) are checked against it —
  including the reverse direction, so a command that no longer exists cannot keep a row.
- **The purity claim names where it is enforced.** `AGENTS.md` said every module outside a
  named set is a pure function; ten writers had accumulated outside that set. The
  inventory is now `FILE_IO_EXIT_MODULES`, checked by an AST scan that finds every module
  that writes, and the paragraph states the count and the test that enforces it.
- **Benchmark structural counts are measured snapshots, not floors.** A `>=` floor answers
  "did we clear a number somebody wrote down", not "did the extraction change": newebpay
  produced 127 error codes against a floor of 80, so losing 47 of them passed silently.
  Counts are asserted with `==`, and recording a snapshot and asserting against it share
  one implementation (`scripts/benchmark_counts.py`) so they cannot measure different
  things.
- **`critical_security_schemes` is checked by identity.** Seven cases declared it and the
  harness never read it, because the declarations were prose labels with no mechanical
  relation to the emitted `components.securitySchemes` keys. The declarations now name the
  emitted key, verified case by case against real output; a human-readable name for a key
  lives in `critical_security_scheme_labels`, which is never matched against output.
  `counts.security_schemes` only ever guarded the cardinality — rename a scheme and the
  count is unchanged.
- **`governance-review-plan` reached the operator manuals**, and a test now asserts that
  every registered CLI command appears in both. The command shipped in 2026-07 and was
  missing from both manuals; nothing would have caught the next one either. Commands
  documented collectively by a sub-app section (`foundry [init|import|approve|list|current]`)
  count through that form, so a new subcommand missing from the brackets still fails.
- **The benchmark case count is compared, not spelled.** Twelve documents wrote the number
  out, and the only guard was a literal `"thirteen unique cases" in text` — which stays
  green after a fourteenth case is added and pins the wrong word in place. The number is
  now read back out of every current document and compared to `REQUIRED_BENCHMARK_CASES`.
  Release notes and ADRs are named separately and pinned to the count they recorded: each
  states what was true when it was written.
- **Issue codes are bound to their routing documents in both directions.** All ten
  `IssueCode` members are listed in the skill's correction reference, in that file's
  `Issue` example, in `AGENTS.md`'s response-by-intent bullets, and in both operator
  manuals. An unlisted code does not leave an incomplete document — it leaves the
  correction loop with no route, and the agent falls back to guessing. The reverse
  direction is checked too: a code deleted from the enum but left in prose has an agent
  responding to a signal that can no longer arrive.
- **Two proofs stopped depending on the clock.** The focus cycle-termination test proves
  termination at a pure-function seam instead of a wall-clock timeout, and the source-risk
  complexity test measures a CPU-cost ratio rather than elapsed time — a loaded machine no
  longer decides whether a correctness proof passes.
- **A PDF case asserts derivability.** `ecpay-creditcard-pdf` re-runs `preprocess` over the
  restored original and asserts byte-identical Markdown wherever the gitignored `raw/` is
  present. This exercises the conversion step of the existing source-backed layer; it is
  not a fifth harness layer and grants no new evidence strength (ADR 0013).
- **Shadow evidence materialization stopped rescanning.** Each exact reference was walking
  the whole fragment list; it now resolves through an index.

## Strategy impact

- [ ] None — <explain why no strategy document changed>
- [x] Updated — `docs/PRODUCT_EXTENSION_ROADMAP.md` (passthrough-gap scope now names `.txt`
  and `.csv`) and `docs/DESIGN_DECISIONS.md` (format-refusal and benchmark-evidence
  sections). ADR 0012 amended to cover plain text and CSV; new accepted record ADR 0013
  (a PDF case asserts derivability, not a second pipeline).

## Validation

- `npm run tag:check` — every tag matches the SemVer policy, no ordering anomaly.
- `uv sync --dev` — resolves cleanly.
- `uv run ruff check .` — pass.
- `npm run docs:check` — pass.
- `uv run pytest --cov=loop_apidoc` — pass, 2385 tests, total coverage 93.57% (floor 92.5%).
- `uv run python scripts/quality_gate.py` — pass in CI-safe mode.
- `uv run python scripts/quality_gate.py --sanitized-fixtures` — pass.
- `uv run python scripts/quality_gate.py --strict-local` — **pass with zero skips**: all
  thirteen required cases have non-empty operator source snapshots, exact required/committed
  parity holds, and every benchmark check executed.

Not run for this release: the manual artifact eyeball spot-check of a fresh representative
run. No extraction, generation, validation, scoring, Foundry, or feedback behaviour changed
in a way that alters a produced artifact, apart from the two additional refused formats,
which are covered by the format tests and the benchmark suite.
