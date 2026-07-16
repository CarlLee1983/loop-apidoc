# Continuous Correction Loop

Use this loop for every non-trivial `loop-apidoc` defect, benchmark drift, or
pipeline quality issue.

> Scope note: this is the **developer** correction loop for fixing the pipeline
> itself. The **agent-runtime** correction loop (severity-gated validation,
> issue-code routing via `target_file`/`field_path`/`requery_scope`, and the
> `--score` loop verdict) is specified in
> `skills/loop-apidoc/reference/assemble-and-correction.md`.

## Rule

No correction is complete until the failure is captured as durable evidence:
a regression test, a benchmark fixture/expectation update, or a documented
follow-up explaining why executable coverage is not practical.

## Loop

1. Reproduce the failure with the smallest command that shows the wrong behavior.
2. Classify the failure boundary:
   - extraction contract or skill prompt;
   - source acquisition (URL catalog/corpus/html snapshot, coverage ledger);
   - source-quality gate (`assess-sources`);
   - manifest/preprocess;
   - plan builder;
   - generator;
   - validator (severity gate, issue routing, score/loop verdict);
   - benchmark expectation;
   - release/operator documentation.
3. Add the regression first:
   - unit/integration test for deterministic code;
   - benchmark extraction/expected update for document-shape regressions;
   - adversarial quality-gate scenario for CLI boundary behavior;
   - `docs/PIPELINE_FOLLOWUPS.md` entry for larger work that should not ship in
     the current patch.
4. Verify the regression fails for the intended reason.
5. Implement the smallest fix at the responsible boundary.
6. Run the focused test, then:
   - `uv run python scripts/quality_gate.py`
   - `uv run python scripts/quality_gate.py --strict-local` when benchmark
     sources are available or benchmark fixtures changed.
7. Update benchmark `notes.md`, expectation files, or follow-up docs with the
   decision and residual risks.

## Quality Gate Commands

Use the default gate for ordinary local validation and CI-safe checks:

```bash
uv run python scripts/quality_gate.py
```

Use strict-local mode before releases and after benchmark fixture changes on a
machine with all `benchmarks/<case>/sources/` directories present:

```bash
uv run python scripts/quality_gate.py --strict-local
```

Strict-local mode fails if benchmark cases skip because local sources are absent.

## Failure Record Template

Add this shape to the relevant benchmark `notes.md`, commit message body, or
`docs/PIPELINE_FOLLOWUPS.md` entry:

```markdown
## Finding

- Symptom:
- Reproduction command:
- Root cause:
- Fix boundary:
- Regression evidence:
- Quality gate:
- Residual risk:
```
