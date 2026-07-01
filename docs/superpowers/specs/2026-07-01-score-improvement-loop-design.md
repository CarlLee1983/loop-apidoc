# Score-Gated Improvement Loop - Design

**Date:** 2026-07-01
**Status:** Approved for planning
**Topic:** Wire the deterministic documentation score into an agent-driven,
score-gated correction loop so `loop-apidoc` runs iterate toward a quality target
instead of stopping the moment validation passes.

## Motivation

Today `loop-apidoc` has two independent quality mechanisms:

- **Validation** (`validate/`) is the hard gate: a run FAILs iff it has any
  `error`-severity issue. The agent's correction loop (SKILL.md steps 5-7, capped
  at 3 rounds) drives re-read -> overwrite extraction JSON -> re-assemble until
  validation passes.
- **Score** (`score/`) is a deterministic, advisory quality signal: it re-projects
  validation issues into weighted categories -> 0-100, and never changes validation
  pass/fail or exit code.

The gap: the agent stops as soon as validation passes (no `error`-severity issues),
even when the score is mediocre because of `warning`-level gaps or low category
scores. Nothing says "keep improving until the documentation reaches a quality
bar." Conversely, there is no principled stopping rule that distinguishes
*reducible* gaps (an agent re-read can fill them) from *irreducible* gaps (the
source genuinely does not state the fact, and the source-grounded invariant forbids
filling them).

This design adds a **score-gated improvement loop**: the existing agent-driven
correction loop keeps iterating until the score reaches a target OR stops improving
(plateau) OR hits a round cap. The stopping rule is the mechanism that separates
reducible from irreducible deficit -- irreducible gaps end the loop via plateau and
are reported honestly rather than fabricated away.

## Decisions (locked during brainstorming)

1. **Driver: agent-session-driven.** Only the agent can re-read sources via
   read-only subagents; the CLI must never extract or re-read. The loop is
   orchestration the agent follows, not an in-code loop. This preserves the
   existing "no deterministic in-code correction loop" architecture.
2. **Stopping rule: score threshold + plateau detection.** Loop until
   `score >= target` OR score does not improve across a round (plateau = hit the
   irreducible source ceiling) OR `max_rounds` reached. Never require
   `ScoreStatus.PASS` -- it is unreachable when the source lacks optional info
   (any `warning`-level finding keeps `findings` non-empty, forcing
   `needs_attention` forever; see `score/evaluate.py:150` `_status`).
3. **Loop-control logic lives in a pure function in `score/`**, surfaced through
   `assemble --score --json`, driven by SKILL.md prose. Policy math is
   deterministic and unit-tested; actuation (re-reading) stays agent-side.

## Goals

1. Add a pure `loop_verdict()` function that, given previous/current score, target,
   round index, cap, and findings, returns a verdict
   (`converged` / `plateau` / `exhausted` / `continue`) plus a reducible/irreducible
   split of the remaining findings.
2. Surface the verdict in `assemble --score --json` via a `loop` block so the
   agent's continue/stop decision is deterministic (read a field, don't re-derive).
3. Rewrite SKILL.md steps 5-7 and `reference/assemble-and-correction.md` so the
   correction loop's acceptance condition is `loop.verdict == converged`, and it
   stops on `plateau`/`exhausted` and presents `irreducible` findings as the honest
   remaining-gap report.
4. Keep the source-grounded invariant intact: never auto-"fix" irreducible/
   fail-closed findings to raise the score; never let the score change validation's
   own pass/fail or the assemble exit code.
5. Full deterministic test coverage of the verdict function and the CLI `loop`
   block, including a plateau-terminates fixture.

## Non-Goals

- No in-code correction loop: the CLI never re-reads sources, never spawns agents,
  never fabricates fills.
- No change to the validation gate: `error`-severity still fails a run
  independently of the score.
- No LLM judgment in scoring or in the verdict function -- both stay deterministic.
- No change to the six-command surface beyond new flags on `assemble`
  (`--target-score`, `--prev-score`, `--round-index`, `--max-rounds`).
- No persistence layer or cross-run score history service; `prev_score` is threaded
  by the agent per session.

## Product Shape

Extend `assemble`:

```bash
loop-apidoc assemble ... --score --target-score 85 --prev-score 72 \
  --round-index 2 --max-rounds 6 --json
```

- `--score` (existing) triggers score evaluation and writes `score/score.{json,md}`.
- `--target-score N` (new) sets the loop target; default resolves from the score
  profile (`ci` -> 85 -- the profile assemble scores under) via
  `DEFAULT_MIN_SCORES` in `score/models.py`.
- `--prev-score N` (new) is the previous round's total score, supplied by the
  agent; absent on round 1. assemble opens a fresh run dir each round
  (`assemble.py:135` collision guard), so previous-round state is threaded by the
  agent, not read from disk -- the CLI stays stateless.
- `--round-index N` (new, default 1) is the current correction round, 1-based.
- `--max-rounds N` (new, default 6) is the round cap; at or beyond it, an
  un-converged run yields `exhausted`.
- When `--score` is present, the `--json` payload gains a `loop` block. The four
  loop flags are no-ops without `--score`.

The agent runs `assemble --score` each round, reads `loop.verdict`, and either
dispatches a targeted read-only subagent for each `loop.actionable` finding (using
its `target_file`/`field_path`/`requery_scope`) or stops and reports
`loop.irreducible`.

## The `loop` block contract

Added to the existing `assemble ... --score --json` payload (which already carries
`run_id`, `run_dir`, `ok`, `status`, `report.issues`, and `score`):

```json
{
  "loop": {
    "verdict": "continue",
    "target": 85,
    "prev_score": 72,
    "curr_score": 80,
    "round_index": 2,
    "max_rounds": 6,
    "actionable": [
      {"code": "REQUIRED_INFO_MISSING", "category": "completeness",
       "target_file": "endpoints/", "field_path": "responses",
       "requery_scope": "POST /charge", "score_impact": 12}
    ],
    "irreducible": [
      {"code": "SOURCE_CONFLICT", "category": "source_grounding",
       "evidence": "...", "score_impact": 50}
    ]
  }
}
```

Verdict values:

- `converged`: `curr_score >= target`. Stop; the run met the quality bar.
- `plateau`: below target and no improvement this round (or nothing reducible left
  to try). Stop; the remaining deficit is irreducible from the current sources.
  `irreducible` explains why.
- `exhausted`: round cap reached without converging. Stop; report both `actionable`
  (unfinished) and `irreducible`.
- `continue`: below target, improved this round, rounds remain, and `actionable` is
  non-empty. Keep going.

**Precedence (evaluated top to bottom; first match wins):**

1. `curr_score >= target` -> `converged`
2. `round_index >= max_rounds` -> `exhausted`
3. `actionable` is empty -> `plateau` (nothing reducible to attempt, including
   round 1 with no reducible findings)
4. `prev_score` is not null AND `curr_score <= prev_score` -> `plateau`
   (no improvement)
5. otherwise -> `continue`

This ordering makes round 1 (`prev_score` null) well-defined: it can only produce
`converged`, `exhausted`, `plateau` (empty actionable), or `continue` -- never
plateau-by-improvement, since there is no previous score to compare.

## Reducible vs irreducible classification

`loop_verdict()` splits the current findings deterministically by code + severity.

**Reducible (actionable -- an agent re-read can plausibly fix):**

- `OPENAPI_INVALID` (error) -- fix upstream JSON/ref, re-assemble.
- `OUTPUT_MISMATCH` (error) -- fix md<->openapi disagreement or an integration ref.
- `REQUIRED_INFO_MISSING` at **error** severity -- re-read the scope and fill.
- `SOURCE_UNVERIFIED` at **error** severity -- add/correct the citation.

**Irreducible (never auto-fixed to raise the score):**

- `SOURCE_CONFLICT` (error) -- report; never silently pick a side.
- `UNSUPPORTED_ASSERTION` (error) -- remove speculation; fail-closed.
- Any finding at **warning** severity -- the source is genuinely silent (missing
  `summary`/`examples`, unsupported/unreadable source, missing review artifacts).

**Boundary note.** `SOURCE_UNVERIFIED` at error severity is classified reducible on
first encounter, but if it survives a genuine re-read the agent treats it as
fail-closed (SKILL.md prose). The verdict function cannot know "after
re-verification"; the **plateau detector is the backstop** -- a finding that
reappears with no score movement forces `plateau` and ends the loop. This keeps the
function pure while the invariant holds.

## Architecture

New pure module:

```text
loop_apidoc/score/loop.py
├── LoopVerdict   (enum: converged | plateau | exhausted | continue)
├── LoopReport    (BaseModel: verdict, target, prev_score, curr_score,
│                  round_index, max_rounds, actionable, irreducible)
└── loop_verdict(*, prev_score, curr_score, target, round_index,
                 max_rounds, findings) -> LoopReport
```

- `loop.py` is pure: no I/O, no subprocess, no network. It consumes an
  already-evaluated `ScoreReport`'s findings plus the round metadata. This matches
  the package boundary rule: only `generate/`, `run/`, `preparation/report.py`,
  `score/report.py`, and `diff/report.py` touch files -- `loop.py` does not.
- Reuses `ScoreFinding` from `score/models.py`; adds no new finding shape.
- The CLI (`cli.py`, assemble `--score` branch, ~lines 245-289) calls
  `evaluate_score()` then `loop_verdict()` and serializes the `loop` block into the
  `--json` payload.

Data flow per round:

```text
agent overwrites extraction JSON in <WORK>
  -> assemble (manifest->plan->prep->generate->validate)     [assemble.py, unchanged]
  -> evaluate_score(inputs)                                  [score/evaluate.py, unchanged]
  -> loop_verdict(prev, curr, target, round, cap, findings)  [score/loop.py, NEW]
  -> --json payload {score, loop}                            [cli.py, MODIFIED]
  -> agent reads loop.verdict
       continue          -> re-read loop.actionable scopes -> overwrite JSON -> next round
       converged         -> stop, run met the quality bar
       plateau/exhausted -> stop, present loop.irreducible as honest gaps
```

## SKILL.md changes (steps 5-7)

`reference/assemble-and-correction.md` and SKILL.md steps 5-7 change from "correct
until validation passes" to:

1. Run `assemble --score --target-score <T> [--prev-score <last>] --json`.
2. Read `loop.verdict`.
   - `continue`: for each `loop.actionable` finding, dispatch a read-only subagent
     to re-read only `requery_scope`, return corrected JSON; overwrite
     `target_file`; carry `curr_score` forward as the next `--prev-score`; repeat.
   - `converged`: stop -- the run met the quality bar.
   - `plateau` / `exhausted`: stop -- present `loop.irreducible` (and any leftover
     `actionable` on exhaustion) as the honest remaining-gap report. **Never
     fabricate to close them.**
3. `max_rounds` default raised from 3 to a configurable cap (proposed default 6) to
   give the score room to climb; the plateau detector prevents wasted rounds.

Validation's own gate is unchanged and still described: an `error`-severity issue
fails the run regardless of score.

## CLI behavior

- `assemble --score` writes `score/score.{json,md}` as today, and now also emits the
  `loop` block in `--json` when `--json` is set.
- assemble exit code is **unchanged**: it still reflects assemble + validation
  semantics only. The loop verdict is advisory and drives the *agent*, not the
  process exit code. A validation FAIL still exits 1; a converged, validation-passing
  run exits 0; score/verdict never override this.
- `--target-score` and `--prev-score` are no-ops unless `--score` is present.

## Error handling

- If scoring hits an input error after assemble produced a run (existing
  `score_error` path, `cli.py:260`), the `loop` block is omitted and `score_error`
  is surfaced, without hiding validation status.
- `loop_verdict()` validates its own inputs: `prev_score`/`curr_score`/`target` in
  0-100, `round_index >= 1`, `max_rounds >= 1`; out-of-range raises `ValueError` at
  the CLI boundary (fail loudly).

## Testing strategy

Unit tests for `loop_verdict()`:

- `curr >= target` -> `converged` (even on the final round).
- below target, `curr <= prev` -> `plateau`.
- below target, `curr > prev`, rounds remain, actionable non-empty -> `continue`.
- `round_index >= max_rounds`, not converged -> `exhausted`.
- round 1 (`prev` null) with empty actionable and not converged -> `plateau`.
- reducible/irreducible split: each code+severity maps to the expected bucket.
- input-range guards raise `ValueError`.

CLI tests:

- `assemble --score --json` emits a `loop` block with the expected verdict and
  buckets.
- `--target-score`/`--prev-score` are respected; absent `--score` -> no `loop`
  block.
- assemble exit code is unchanged by the verdict.

Integration/fixture test:

- a run whose only remaining findings are `warning`-level source-silent gaps
  terminates at `plateau` (does not spin to `exhausted`), and the gaps appear in
  `irreducible`.

## Acceptance criteria

1. `loop_verdict()` exists as a pure function in `score/loop.py` and is fully
   unit-tested.
2. `assemble --score --json` emits a stable `loop` block with `verdict`, round
   metadata, and reducible/irreducible finding buckets.
3. SKILL.md steps 5-7 and `reference/assemble-and-correction.md` drive the loop off
   `loop.verdict`, stopping on `converged`/`plateau`/`exhausted`.
4. Irreducible/fail-closed findings are never auto-fixed to raise the score; the
   source-grounded invariant holds.
5. The score never changes validation pass/fail or the assemble exit code.
6. A source-silent-only run terminates at `plateau` rather than exhausting rounds.

## Future

The `loop` block is the same acceptance-gate contract a future code-to-document
workflow would consume: extract routes/schemas -> `inventory.json` + `endpoints/*`
-> `assemble --score` -> iterate on `loop.verdict`. Keeping the verdict pure and
CLI-surfaced means that workflow reuses this loop unchanged.
