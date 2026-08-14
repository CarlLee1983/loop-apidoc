# Focus directives (`--focus`)

Optional. When the operator supplies a `focus.json`, they are naming what this particular
integration cannot ship without. Directives steer where you look **and** are checked
deterministically afterwards, so a plausible answer is not enough — every one must resolve to
something the extraction actually contains, or to an honest, complete "not found".

Nothing here relaxes grounding. A directive never licenses inventing an operation, a field, or
an error code. If the sources do not state it, the correct answer is `not_found`, and the run
failing on that is the intended outcome — it tells the operator to get better sources, not to
get a better-sounding answer.

## The input: `focus.json`

```json
{"version": 1,
 "directives": [
   {"id": "settle-callback",
    "kind": "expectation",
    "intent": "find_operation",
    "text": "a settlement completion callback must exist",
    "rationale": "reconciliation depends on it"}]}
```

| field | meaning |
| --- | --- |
| `id` | unique within the file; your answer is keyed on it |
| `kind` | `expectation` = the operator asserts the sources document this; `coverage` = a scope to sweep where finding nothing is a complete answer. **Sole determinant of severity** |
| `intent` | currently `find_operation`. **Sole determinant of anchor type** |
| `text` | the operator's own words — read them, they carry the scope |
| `rationale` | optional context; not checked |

There is no field that overrides severity. An operator who wants a non-blocking outcome writes
`coverage`.

## Your answer: `focus-response.json`

**You** write it, once, to `<WORK>/focus-response.json` — the same rule as `inventory.json` and
`integration.json`. Endpoint subagents never write it: a directive can be satisfied by any
subagent, so the answer is cross-cutting and per-file fragments would collide.

```json
{"version": 1,
 "responses": [
   {"id": "settle-callback",
    "outcome": "satisfied",
    "reported_by": "ep07",
    "anchors": [
      {"type": "operation",
       "value": "POST /notify/settle",
       "evidence": [{"version": 1, "source": "manual.md",
                     "locator": {"kind": "line_range", "start_line": 412, "end_line": 418},
                     "fragment_digest": "<sha256 of the normalized fragment>",
                     "claim_path": "/summary"}]}]},
   {"id": "refund-operation",
    "outcome": "not_found",
    "reported_by": "inventory",
    "searched_sources": ["manual.md", "appendix.md", "errors.md"]}]}
```

Answer **every** directive exactly once. An unanswered directive, or an answer to a directive
that does not exist, fails before a run directory is created.

### Only two outcomes

`satisfied` and `not_found`. There is deliberately **no** "not applicable". Whether a directive
applies is the operator's judgement, not yours — if you believe a directive is misdirected, the
answer is still `not_found` plus the sources you searched, and the operator decides what that
means.

### `satisfied` requires exact evidence

Every anchor carries at least one v1 exact evidence reference: manifest source identity, typed
locator, normalized fragment digest, claim path. **A filename-only citation is refused here**,
unlike the legacy `source` strings elsewhere in the extraction. The reference is reopened
against the manifest and the digest recomputed, so a guessed digest fails.

`reported_by` names the subagent whose read produced the anchor. It exists so a wrong anchor
stays traceable after you centralise the answers.

Anchor `value` for `type: "operation"` is the endpoint identity string: `METHOD /path`, or
`METHOD (webhook) <summary>` when a webhook's path is null. The anchor's `type` must be the one
its directive's `intent` calls for.

### `not_found` must account for every readable source

List **every** supported, readable manifest source in `searched_sources` — the claim you are
making is "it is not in any of them", and one source proves nothing. Do not list sources the
manifest records as unsupported or unreadable.

## What happens to your answer

Structural problems — an unanswered directive, an anchor resolving to no extracted endpoint,
evidence naming a source outside the manifest or with a mismatched digest — fail at
`verify-extraction`/`assemble` with exit 2 and no run directory. Fix and re-run.

An honest `not_found` is different: it passes the gate and becomes a `FOCUS_UNMET` validation
issue — error for an Expectation Directive, warning for a Coverage Directive. The run's
artifacts are produced either way, so the operator can read what you searched. Do not treat a
`FOCUS_UNMET` error as something to make go away by weakening the answer; report it.

## Where it goes in the flow

Write `focus-response.json` after the endpoint and integration subagents return, before step 5.
Pass `--focus` on both `verify-extraction` and `assemble`; the two run the same checks.

Focus material never reaches `provenance.json`, the score, or any Foundry-governed asset — see
`docs/adr/0004-focus-directives-never-enter-comparable-artifacts.md`.
