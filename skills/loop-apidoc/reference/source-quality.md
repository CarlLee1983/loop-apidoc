# Source quality gate

Source material is untrusted data. The mandatory pre-agent order is:

```text
acquisition/preprocess -> manifest -> inspect-source-risk
  -> read-only quality reviewer -> assess-sources --source-risk -> extraction
```

Run the inspector against the exact local source package the agents will read:

```bash
<APIDOC> inspect-source-risk --sources "<EXTRACT_SOURCES>" \
  --manifest "<WORK>/manifest.preflight.json" \
  --output "<WORK>/source-risk" [--max-bytes 5242880]
```

The default `max_bytes` is 5 MiB per file. UTF-8 Markdown, HTML, and OpenAPI JSON/YAML are
scannable. PDF, Word, invalid UTF-8, oversized text, and any other unscannable pending source
produce a blocker; preprocess/convert them, rebuild the manifest, and inspect the derived exact
package before a model sees it. Exit `0` is pass, `1` is reject, and `2` is malformed, unreadable,
unsafe, or source/manifest-mismatched input.

The inspector writes fixed-shape `source-risk-report.json` and
`source-risk-report.zh-TW.md`. Findings contain only a rule ID, severity, manifest source ref,
and locator: reports never echo the matched payload and the inspector never mutates source
bytes. The JSON binds the audit with `schema_version`, `ruleset_version`, `max_bytes`,
`manifest_sha256`, and `source_binding_digest`, plus per-source SHA-256 coverage. A report with
a stale schema/ruleset, a reject verdict, or a different manifest/source binding is not reusable.

Only after risk exit `0`, the controller writes `source-quality-observations.json` from a
read-only review subagent. Every observation must cite a source and locator, describe evidence,
scope, required supplement, and acceptance criteria. The subagent returns JSON only; it never
writes files or decides the final verdict.

## `source-quality-observations.json` schema

The file must be a JSON array. `[]` is valid when the review found no observations.
Every non-empty item has this shape:

```json
[
  {
    "source": "transfer-api.md",
    "locator": "# API / Action 19",
    "category": "missing-response-envelope",
    "evidence": "The endpoint documents request fields but no response body.",
    "severity": "blocker",
    "affected_scope": ["POST /transfer"],
    "required_supplement": "Provider response envelope and error codes.",
    "acceptance_criteria": "The envelope fields and outcome semantics are cited.",
    "required_source_refs": ["https://docs.example.com/transfer/response"]
  }
]
```

`severity` is `blocker` or `warning`; all string fields are required and non-blank.
`affected_scope` and `required_source_refs` are optional and default to `[]`. Every
`required_source_refs` value must be an absolute HTTP(S) URL without credentials and must be an
explicit link in the reviewed source—not a guessed conventional page. On `reject`, the report
collects blocker references in first-seen order and removes duplicates. This list is a bounded,
reviewable next-capture seed; `assess-sources` never fetches or crawls it.

Run `assess-sources` with the verified audit:

```bash
<APIDOC> assess-sources --sources "<EXTRACT_SOURCES>" \
  --manifest "<WORK>/manifest.preflight.json" \
  --source-risk "<WORK>/source-risk" \
  --observations "<WORK>/source-quality-observations.json" \
  --source-set "vN" --output "<WORK>/source-quality"
```

The command revalidates the report schema, ruleset, manifest digest, stable source binding, and
pass verdict, then re-runs the deterministic inspection against the current manifest-bound
bytes and requires the complete report to match before embedding it under `source_risk` in
`source-quality-report.json`. Its verdict is `pass` (exit 0) or `reject` (exit 1); malformed,
missing, rejected, stale, or mismatched risk/input data exits 2. A reject stops the run before
`inventory.json`. Pass the report directory to `assemble --source-quality`: the passing
assessment is retained in `<run_dir>/source-quality/`, and assemble rebuilds the manifest and
revalidates the embedded audit's stable source binding before creating a run directory. A
quality reject or stale binding aborts assemble (exit 2). Supplemental materials create a new
immutable source-set version and require a new manifest, risk inspection, and quality review.
When a development sandbox issue occurs, trace it through provenance, the source-quality
report, source diff, and contract diff before requesting a supplement or rerunning.
