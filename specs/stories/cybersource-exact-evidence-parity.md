# Bring cybersource-payments to claim-complete exact-evidence parity

## Goal

ADR 0016 makes Core graduation wait for exact-evidence parity on every restored
source-backed benchmark. `cybersource-payments` cites 25 Markdown sources in the
gitignored `sources/`, restored as recorded in the case's `notes.md`. Its replay today is
legacy `passed` / Core `accept` with 38 Core claims, all unverified.

One of those sources is the SDK `README.md`. The manifest scanner ignores every
`README*` file (`DEFAULT_EXCLUDES` in `loop_apidoc/manifest/scanner.py`), so the
committed `url_sources/source-manifest.json` records it as `ignored` with no SHA-256, and
no evidence can cite it. The local copy matches the client repository at commit
`a9dde2993c9c7ccb5ad0267822a9dd475823b19d` byte for byte (SHA-256
`124b39bcc49b3cb03042835641bd4fe4bbc36f4f3a90877522fda129556729fa`). Rename it to
`client-README.md` and update every extraction `source` that cites `README.md`.

Then bind every material claim in the committed extraction to v1 `evidence[]` with exact
`line_range` locators on the 25 sources, and add the case to the exact-evidence parity
lane, so `test_case_obeys_declared_core_parity_contract` replays it.

Core accepts a `line_range` reference as claim-bound support without comparing its text
to the claim value. This Story therefore holds every reference to the **range rule** of
`specs/stories/ecpay-exact-evidence-parity.md` (clauses 1 to 4, with its `flat`), applied
to the source each entry names, with these changes:

- Clause 4's identifiers are: schema `/name`, `schema_ref`, environment `/name`, the
  field-condition `/name` (its scope), integration `/kind`, and `/operation_refs/<ref>`.
- **Clause 5 (types).** A schema field's `/type` is a normalized SDK type. Its range
  must contain the table row of that field, and that row's Type cell must map to the
  claimed type: `**str**` to `string`, `**bool**` to `boolean`, `**int**` to `integer`,
  `**float**` to `number`, a `list[...]` type (bold or linked) to `array`, and a linked
  model `[**Name**](Name.md)` to `object`. Clause 2 does not apply to `/type`.

Each string that fails clause 2 today is a paraphrase. Correct it to text that appears in
the cited section of its source:

- The `summary` of the operations whose summary is not source text, and the `description`
  of all six operation responses (five `201`, one `400`).
- The `topic` and `detail` of the four `operational` entries. A `topic` that is not
  source text becomes the heading of the section that its `source` names.
- The `name` of each `crypto` entry that is not source text, which becomes the heading of
  the README section it cites.
- The `when` of the three `field_conditions`, and the `name` of the one `test_cases`
  entry.
- The `type` of the two security schemes, which becomes the README's
  `authentication_type` value: `HTTP_Signature` and `JWT`.

The `Production` environment is moved to `missing`. The source gives only the host
`api.cybersource.com`, as an SDK `run_environment` setting, and states no URL scheme.

## Out of Scope

- Any change under `loop_apidoc/`. If a claim cannot be supported with the existing
  pipeline, stop and report it.
- Any source other than the 25 restored files. On a SHA-256 mismatch against
  `url_sources/source-manifest.json`, or against the README hash above, stop.
- Committing anything under `sources/`, `source-quality/`, or `work/`.
- Changing extracted values other than the corrections listed in the Goal, and
  renaming any identifier listed in clause 4.
- Changing the type normalization of any schema field.
- `expected/core-parity.json`, and the other cases without parity.
- ADR 0016 and the CI workflow.

## Acceptance Criteria

1. `shasum -a 256 benchmarks/cybersource-payments/sources/client-README.md` reports
   `124b39bcc49b3cb03042835641bd4fe4bbc36f4f3a90877522fda129556729fa`, and
   `benchmarks/cybersource-payments/sources/README.md` does not exist. The completion
   report shows both commands.
2. `uv run loop-apidoc manifest --sources benchmarks/cybersource-payments/sources --output benchmarks/cybersource-payments/url_sources/source-manifest.json`
   regenerates the committed manifest. In it, `client-README.md` is `supported` with
   that SHA-256, no entry is `ignored`, and the other 24 entries keep the SHA-256 they
   have on `main`.
3. `grep -rn '"README.md' benchmarks/cybersource-payments/extraction` prints nothing.
4. `uv run loop-apidoc verify-extraction --sources benchmarks/cybersource-payments/sources --extraction benchmarks/cybersource-payments/extraction`
   exits 0.
5. A script outside the repository applies the range rule, with clause 5, to every
   `evidence` entry under `benchmarks/cybersource-payments/extraction/`. It prints the
   number of entries it checked and the number of violations, and the violation count
   is 0. The script and its output are in the completion report.
6. `"cybersource-payments"` is a member of `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES` in
   `scripts/quality_gate.py`.
7. `uv run pytest tests/test_benchmarks.py -k "cybersource" -rA` reports no failures and
   no skips, and lists
   `test_case_obeys_declared_core_parity_contract[cybersource-payments]` as passed.
8. A script loads each file under `benchmarks/cybersource-payments/extraction/` on both
   sides of `main...HEAD`, deletes every `evidence` key, and prints the remaining
   differences. Each one is a correction listed in the Goal, the `README.md` to
   `client-README.md` rename in a `source` string, the removed `Production` environment,
   or its new `missing` entry. Its output is in the completion report.
9. `git diff main...HEAD -- benchmarks/cybersource-payments/expected/minimum.json`
   changes only `counts.servers`, from `2` to `1`, recorded with
   `scripts/benchmark_counts.py --record`.
10. `git diff --name-status main...HEAD -- benchmarks/cybersource-payments/expected/validation.expect.json`
    prints nothing, or its diff changes only `current_issue_classes` counts and their
    explanatory text and names each warning that was added or removed.
11. `benchmarks/cybersource-payments/notes.md` records the parity result, the README
    rename and why, the range rule with clause 5, the corrections, and the `Production`
    move. `docs/PRODUCT_EXTENSION_ROADMAP.md` and `docs/BENCHMARK_VALIDATION_PLAN.md` name
    CyberSource as a parity case. Every parity count they state equals the number of
    members of `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`.
12. `git ls-files benchmarks/cybersource-payments/sources benchmarks/cybersource-payments/source-quality benchmarks/cybersource-payments/work`
    prints nothing.
13. `git diff --name-status main...HEAD` lists only files under
    `benchmarks/cybersource-payments/extraction/`,
    `benchmarks/cybersource-payments/notes.md`,
    `benchmarks/cybersource-payments/url_sources/source-manifest.json`,
    `benchmarks/cybersource-payments/expected/minimum.json`,
    `benchmarks/cybersource-payments/expected/validation.expect.json`,
    `scripts/quality_gate.py`, `tests/test_quality_gate.py`,
    `docs/PRODUCT_EXTENSION_ROADMAP.md`, `docs/BENCHMARK_VALIDATION_PLAN.md`, and this
    Story file (`specs/stories/cybersource-exact-evidence-parity.md`).
14. `make verify` exits 0.
