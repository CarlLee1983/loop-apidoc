# Extraction Write Contract + `verify-extraction` — Design

**Date:** 2026-07-09
**Status:** Approved for planning
**Topic:** Let endpoint subagents write their own `endpoints/ep<N>.json`, and expose
the assemble input boundary as a standalone `verify-extraction` command that both
entry points share.

**Issue:** [#5](https://github.com/CarlLee1983/loop-apidoc/issues/5) — 子代理契約「orchestrator
是唯一寫入者」在端點數量大時造成不必要的 context 成本

## Motivation

`skills/loop-apidoc/SKILL.md` states the extraction subagent contract as:

> The subagent **returns the JSON only** — no prose, no file writes.
> **You (the orchestrator) are the only writer.**

The rule exists to keep extraction controllable and traceable: a subagent that writes
wherever it likes can corrupt provenance. But it achieves that goal by **transport** —
every endpoint's JSON must flow through the orchestrator's context solely so the
orchestrator can write it back out verbatim.

The reporter measured the cost on a 17-endpoint document: each endpoint JSON is
2–4k tokens, so tens of thousands of tokens are spent on pure carriage. They worked
around it by having each subagent write its own `ep<N>.json`, returning one line
(`ep05 OK 8 params 1 responses`), then validating the result with an ad-hoc script.
All 17 files were consistent, 106 parameters, zero violations. The contract's *purpose*
was met at an order of magnitude less cost.

**The purpose is achievable by verification rather than by transport.** This design
makes that swap official, and ships the verifier so every user does not rewrite it —
differently — themselves.

## Scope

In scope:

- Relax the subagent write contract for `endpoints/ep<N>.json` only.
- Add cross-file invariants (endpoint files ↔ inventory) to the existing assemble
  input boundary.
- Add a `verify-extraction` CLI command that runs that same boundary standalone.

Explicitly **not** in scope (YAGNI):

- Relaxing the write contract for `inventory.json` or `integration.json`. Inventory is
  the global truth the endpoint files are checked against, and the orchestrator needs
  it in context to assign endpoint work. The reporter's transcript-scraping workaround
  for inventory is not adopted.
- Index-strict `ep<N>.json` ↔ `inventory.endpoints[N]` correspondence. See
  [Rejected alternatives](#rejected-alternatives).
- Any general-purpose plugin/extension mechanism for custom checks.

## The contract, after

`SKILL.md`'s subagent contract becomes a layered write permission:

| Actor | May write | Must not write |
| --- | --- | --- |
| endpoint subagent | exactly the one `endpoints/ep<N>.json` assigned to it | `inventory.json`, `integration.json`, any other subagent's file |
| inventory subagent | nothing (returns JSON) | anything |
| integration subagent | nothing (returns JSON) | anything |
| orchestrator | `inventory.json`, `integration.json` | — |

An endpoint subagent returns **one line** of summary (e.g. `ep05 OK 8 params 1 responses`),
not the JSON body. The orchestrator:

1. writes `inventory.json` from the inventory subagent's returned object;
2. assigns each `inventory.endpoints` entry a filename and dispatches one subagent per
   entry, telling it the exact path to write;
3. runs `verify-extraction`;
4. runs `assemble`.

The orchestrator's job shifts from **carriage** to **verification**. The grounding rule
and the read-only posture toward *sources* are unchanged — a subagent still only reads
sources and never fetches the web.

## The gate: one definition, two entry points

The assemble input boundary becomes a single pure aggregator that `assemble` and
`verify-extraction` both call. Neither can drift from the other.

```
check_extraction(inventory, endpoints, integration, manifest) -> list[str]
  ├─ input_schema.py    typed pydantic guards, localized-key rejection   (exists)
  ├─ source_guard.py    endpoints[].path rooting + source citation format (exists)
  └─ cross_file.py      endpoint files ↔ inventory                        (new)
```

`cross_file.py` is pure, no file I/O, consistent with the package boundary rule in
`CLAUDE.md`.

### New cross-file invariants

All are `error` severity — a violation means `exit 2` and no run directory:

1. `len(endpoints/*.json) == len(inventory.endpoints)`
2. The `(method, path)` multiset of the endpoint files equals that of `inventory.endpoints`.
3. No `(method, path)` appears in two endpoint files.
4. Every `schema_ref` (in `request` and in each `responses[]`) resolves to an
   `inventory.schemas[].name`.
5. Every `security[]` entry resolves to an `inventory.security_schemes[].name`.

Invariant 3 is what catches the failure mode that actually loses data: two subagents
writing the same endpoint while a third endpoint goes unwritten. Invariants 1 and 2
alone would let that pass only if counts coincidentally matched; together the three
close it.

Parameter localized-key rejection is already covered by `input_schema.ParamEntry`
and is not restated here.

### Empirical safety

These five invariants were run against all 10 benchmark cases (55 endpoint files)
before this design was accepted: **zero violations**. Making them blocking in
`assemble` therefore breaks no existing case. The benchmark harness will assert this
continuously (see [Testing](#testing)).

## CLI

```
loop-apidoc verify-extraction \
    --sources <SOURCES> \
    --extraction <WORK> \
    [--url <URL> ...] [--exclude <GLOB> ...] [--json]
```

- Builds a manifest (needed to check `source` citations), runs `check_extraction`,
  writes nothing, creates no run directory.
- `exit 0` when clean; `exit 2` with every violation listed at once. Not `1` —
  `1` means validation FAIL, and this command never validates outputs.
- `--json` emits the violations as an array so the orchestrating agent can consume
  them without parsing prose.
- `--sources` is required for the same reason `assemble` requires it: `source`
  citations are checked against `manifest.json`.

Hard schema errors (malformed JSON, wrong types) still raise `AssembleInputError` from
`load_extraction_inputs` and abort on the first one — they make the remaining checks
meaningless. Path/source/cross-file violations are collected and reported together,
because their fix is one rewrite of the extraction JSON, not a per-violation round trip.

## Error handling

`assemble` behaviour is unchanged in shape: `AssembleInputError` → `exit 2`, no orphan
run directory (guaranteed by the batch-B change that builds the manifest before
`run_dir.mkdir()`). The only difference is that the gate now also carries the
cross-file invariants.

Failure modes and who catches them:

| Failure | Caught by |
| --- | --- |
| a subagent dies, writes nothing | invariant 1 (count) |
| a subagent writes invalid JSON | `load_extraction_inputs` |
| a subagent writes an endpoint not in inventory | invariant 2 |
| two subagents write the same endpoint | invariant 3 |
| a subagent invents a schema/security name | invariants 4, 5 |
| a subagent uses localized keys | `input_schema.ParamEntry` |
| a subagent writes `inventory.json` | not detectable; prohibited by contract |

The last row is an accepted residual risk. It was equally undetectable under the old
contract, where a rogue subagent could return fabricated JSON that the orchestrator
would then dutifully write.

## Testing

- One unit test per cross-file invariant, TDD (red before green), in
  `tests/agentcli/test_cross_file.py`.
- `check_extraction` composition test: a single input violating two layers reports
  violations from both.
- CLI tests: `exit 0` on a clean extraction dir, `exit 2` listing all violations,
  `--json` shape, and that no run directory is created.
- Benchmark harness: every benchmark case's `extraction/` directory must pass
  `check_extraction` against its own manifest. This is the regression net that caught
  index-strict correspondence during design; it will catch the next over-tight
  invariant the same way.

## Rejected alternatives

**Index-strict `ep<N>.json` ↔ `inventory.endpoints[N]`.** Initially chosen, then
rejected on evidence. Measurement showed `apis-guru-baseline` already violates it
(`ep3`/`ep4`/`ep5` are out of position), and filename zero-padding is inconsistent
across cases (`ep0` vs `ep00`), so the rule would need a padding-parse convention.
It would also contradict `extraction-schemas.md`'s existing "a stray order is not
fatal". Against that cost, the only extra failure mode it detects — two files' contents
swapped — has **no downstream consequence**, because generation keys on `method`/`path`
and never on the filename. The set-based invariants catch every failure that loses data.

**Checks only in `verify-extraction`, `assemble` unchanged.** Rejected: a user who
forgets to run the verifier gets no protection, and two check implementations drift.

**`assemble --check-only` instead of a new command.** Rejected: it makes `assemble`'s
contract conditional ("sometimes assembles"), and still forces `--output` to be supplied
for a run directory that is never created.

**Relaxing the inventory write contract too.** Rejected for now. It is the largest single
token win (~18k), but the orchestrator needs the inventory in context to assign endpoint
scopes, and it is the reference every cross-file invariant checks against. Revisit only
with a measured case where inventory carriage, not endpoint carriage, is the bottleneck.
