# API Documentation Score Reports - Design

**Date:** 2026-07-01
**Status:** Approved for planning
**Topic:** Add first-class API documentation scoring so completed
`loop-apidoc` runs can produce machine-readable and human-readable quality
reports.

## Motivation

`loop-apidoc` already produces source-grounded API documentation artifacts:

- `openapi.yaml`
- `api-guide.zh-TW.md`
- `review.html`
- `provenance.json`
- `integration-contract.json`
- `examples/`
- `handoff/`
- `validation/report.{json,md}`

These artifacts prove whether a run is structurally valid and source-grounded,
but they do not give a compact quality signal for CI, release review, customer
document intake, or future code-to-document workflows. Users need a clear answer
to "Is this API documentation good enough to hand off?" plus enough detail to
fix the highest-impact gaps.

The scoring feature makes documentation quality a first-class output. It
summarizes existing run artifacts into a status, total score, category scores,
blocking findings, and remediation guidance without re-reading sources or using
LLM judgment.

## Goals

1. Add a formal `loop-apidoc score` command for completed run directories.
2. Write both JSON and Markdown score reports under each scored run directory.
3. Support CI and human review with the same report shape.
4. Keep scoring deterministic and artifact-driven.
5. Support configurable strictness through `--profile ci|review` and
   `--min-score`.
6. Let `assemble` optionally write score reports after generating a run.
7. Establish the same scoring model as the future acceptance gate for
   code-to-document generation.

## Non-Goals

- No direct codebase route/controller/schema extraction in this MVP.
- No LLM-based quality judgment.
- No re-fetching URLs, re-reading original source files, or inferring missing
  facts.
- No replacement for `validation/report.{json,md}`.
- No separate quality database, trend dashboard, or hosted service.
- No change to the core source-grounded invariant: unsupported assertions remain
  failures or findings, not opportunities for scoring guesses.

## Product Shape

Add a first-class CLI command:

```bash
loop-apidoc score --output <run-dir> [--profile ci|review] [--min-score 80] [--json]
```

The command scores an existing run directory. It reads:

- `validation/report.json`
- `provenance.json`
- `openapi.yaml`
- `manifest.json`
- `plan/normalization-plan.json` when present

It writes:

```text
<run-dir>/score/
├── score.json
└── score.md
```

The `--json` flag prints the score report JSON to stdout for CI and agent
callers. The file reports are still written.

Add an optional assemble integration:

```bash
loop-apidoc assemble ... --score
```

`assemble --score` writes the score reports after the run directory is produced.
It does not change the existing assemble contract: validation status still
drives assemble's original exit semantics, and scoring reflects the resulting
artifacts.

## Score Report Contract

`score.json` has a stable machine-readable shape:

```json
{
  "status": "pass",
  "score": 86,
  "profile": "ci",
  "min_score": 85,
  "category_scores": {
    "openapi_validity": 100,
    "completeness": 78,
    "consistency": 90,
    "source_grounding": 85,
    "reviewability": 80
  },
  "blocking_findings": [],
  "findings": []
}
```

Status values:

- `pass`: no blocking findings, total score is at or above `min_score`, and all
  required category gates pass.
- `needs_attention`: no blocking findings, but warnings, low category scores, or
  non-blocking gaps remain.
- `fail`: one or more blocking findings exist, or total score is below
  `min_score`.

Findings preserve the useful fields from validation issues:

- `code`
- `severity`
- `location`
- `evidence`
- `suggested_fix`
- derived `category`
- derived `blocking`
- derived score impact

`score.md` is the human-readable view. It should include:

1. Overall status and score.
2. Profile and threshold.
3. Category score table.
4. Blocking findings.
5. Non-blocking findings and warnings.
6. Highest-impact recommended fixes.
7. Links back to `validation/report.md`, `review.html`, and primary artifacts.

## Score Categories

MVP weights:

| Category | Weight | Inputs |
| --- | ---: | --- |
| `openapi_validity` | 20 | `OPENAPI_INVALID`, OpenAPI parse/load status |
| `completeness` | 30 | `REQUIRED_INFO_MISSING`, missing required integration details |
| `consistency` | 20 | `OUTPUT_MISMATCH`, artifact disagreement |
| `source_grounding` | 20 | `SOURCE_UNVERIFIED`, `UNSUPPORTED_ASSERTION`, provenance coverage |
| `reviewability` | 10 | `review.html`, manifest coverage, report availability, actionable fixes |

Each category starts at 100 and loses points from findings in that category.
The weighted total is rounded to an integer from 0 to 100. Penalty constants
should live in one place so future tuning is explicit and testable.

The scorer must keep the validation report as the source of truth for issue
severity. It may derive stricter blocking behavior by profile, but it must not
silently downgrade validation errors.

## Profiles

`ci` is strict and optimized for release gates:

- default `min_score`: 85
- source-unverified errors are blocking
- required connection information missing at error severity is blocking
- OpenAPI invalidity is blocking
- output mismatch errors are blocking

`review` is optimized for human intake and customer document triage:

- default `min_score`: 70
- structural errors remain blocking
- more content gaps can remain `needs_attention`
- warnings reduce score and appear as fix recommendations

An explicit `--min-score` overrides the profile default. It does not change
which findings are blocking; it only changes the total score threshold.

## Architecture

Add a dedicated package:

```text
loop_apidoc/score/
├── __init__.py
├── models.py
├── loader.py
├── evaluate.py
└── report.py
```

Responsibilities:

- `models.py`: `ScoreReport`, `ScoreFinding`, `ScoreCategory`,
  `ScoreStatus`, `ScoreProfile`, and input error types.
- `loader.py`: read and parse run directory artifacts, returning a structured
  input object or a deterministic input error.
- `evaluate.py`: pure scoring logic from loaded artifacts plus profile options
  to `ScoreReport`.
- `report.py`: write `score.json` and `score.md`.

Public data flow:

```text
run-dir artifacts
  -> score.loader.load_score_inputs()
  -> score.evaluate.evaluate_score()
  -> score.report.write_score_reports()
  -> CLI exit/status
```

`evaluate.py` must be pure: no file I/O, no subprocesses, no network, no source
document reads.

## CLI Behavior

`loop-apidoc score --output <run-dir>` exit codes:

- `0`: score status is `pass`
- `1`: score status is `needs_attention` or `fail`
- `2`: input error, such as missing required files or invalid JSON/YAML

`loop-apidoc assemble ... --score` behavior:

- assemble still returns its existing exit code based on assemble and validation
  semantics.
- score reports are written whenever the run directory and score inputs are
  available.
- if scoring itself hits an input error after assemble produced a run, assemble
  should surface that error clearly without hiding validation status.

## Error Handling

The score command returns exit `2` for deterministic input failures:

- missing `validation/report.json`
- missing `openapi.yaml`
- missing `provenance.json`
- missing `manifest.json`
- invalid JSON in required JSON artifacts
- invalid YAML in `openapi.yaml`

Error messages must name the file and the parse/load problem. They should not
attempt to repair the run directory.

## Future Code-to-Document Workflow

The MVP deliberately stops at score reports. Future code-to-document generation
can reuse this standard by producing the same extraction and run artifacts:

```text
code project
  -> route/schema/test extraction
  -> inventory.json + endpoints/*.json
  -> assemble
  -> score
```

This keeps code extraction outside the scoring boundary. The score report becomes
the shared acceptance contract for documentation generated from PDFs, Markdown,
OpenAPI sources, URLs, or codebases.

## Testing Strategy

Unit tests for `evaluate_score()`:

- no validation issues produces a high score and `pass`
- blocking validation errors produce `fail`
- warnings produce `needs_attention`
- `ci` and `review` profiles apply different default thresholds and blocking
  behavior
- explicit `--min-score` changes threshold behavior
- category penalties affect the expected weighted total

Loader and report tests:

- missing required files produce input errors
- invalid JSON/YAML produces input errors naming the file
- `score.json` preserves the stable schema
- `score.md` includes overall status, category scores, blocking findings, and
  recommended fixes

CLI tests:

- `loop-apidoc score --output <run-dir> --json` prints JSON and writes reports
- pass returns exit `0`
- needs-attention/fail returns exit `1`
- input errors return exit `2`
- `assemble --score` writes `score/score.json` and `score/score.md`

## Acceptance Criteria

1. A completed run directory can be scored with `loop-apidoc score`.
2. Score reports are written to `<run-dir>/score/score.{json,md}`.
3. JSON output is stable enough for CI and agent parsing.
4. Markdown output is readable enough for human review.
5. `ci` and `review` profiles produce different threshold behavior.
6. Input errors are deterministic and use exit code `2`.
7. Scoring does not infer missing source facts.
8. `assemble --score` can write reports without changing the existing assemble
   validation contract.
