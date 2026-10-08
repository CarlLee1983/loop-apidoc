# Bring ecpay-creditcard-pdf to claim-complete exact-evidence parity

## Goal

ADR 0016 makes Core graduation wait for exact-evidence parity on every restored
source-backed benchmark. Four cases meet it today, the members of
`EXACT_EVIDENCE_PARITY_BENCHMARK_CASES` in `scripts/quality_gate.py`.
`ecpay-creditcard-pdf` cites one derived Markdown source. `source-derivation.json`
binds the original PDF (`raw/gw_p110.pdf`, SHA-256
`fd12a38c37df000e0927d39fdc32448c304b10e8aa6056d4419c63c42b7f53e9`) to the Markdown
that `loop-apidoc preprocess` derives from it (`sources/gw_p110.pdf.md`, SHA-256
`d42d3337d15d4c91ffad0e8efa48b294e9e1404149f20ae73b70b040cbe650b4`).

Restore that Markdown into the gitignored `sources/`, and bind every material claim in
the committed extraction to v1 `evidence[]` with exact `line_range` locators on
`gw_p110.pdf.md`. Then add the case to the exact-evidence parity lane, so
`test_case_obeys_declared_core_parity_contract` replays it. The
`field-condition-claim-identity` Story (merged in #186) is a prerequisite, because the
case has three field conditions on `AioCheckOutRequest`.

Core accepts a `line_range` reference as claim-bound support without comparing its
text to the claim value. This Story therefore holds every reference to the
**range rule** below and checks it with a script. Under that rule, a claim string
value has to be source text.

**Range rule.** For an evidence entry, let `v` be
`claim_value_at(claim_kind, value, claim_path)` from `loop_apidoc/domain/claim_paths.py`,
and let `flat(s)` remove `*`, `|`, and `<br>`, then collapse every whitespace run to a
single space.

1. Every range spans at most 40 lines.
2. If `v` is a string and not an identifier listed below, `flat(v)` is a substring of
   `flat(range text)`.
3. If `v` is not a string, as with a `required` flag, the range text contains the name
   of the field or parameter that the path belongs to. For a dotted field name, that is
   its last segment without `[]`.
4. The source states no name for these identifiers: schema `/name`, operation
   `/responses/<status>/schema_ref`, environment `/name`, the field-condition `/name`
   (its scope schema), integration `/kind`, `/operation_refs/<ref>`, and the
   `PaymentResultResponse` field `response`. The source says that reply has
   "並無參數名稱". For each identifier, the evidence uses a range that the same item
   also cites for a path held to clause 2 or 3. For a dotted schema field name, clause 2
   applies to its last segment without `[]`.

Each string that fails clause 2 today is a paraphrase. Correct it to text that appears in
the cited section of `gw_p110.pdf.md`:

- The `summary` and `200` response `description` of the four operations.
- The `meaning` of the seven `errors`.
- The `topic` and `detail` of the seven `operational` entries. Each `topic` becomes the
  heading of the section that its `source` names.
- The `name`, `verification`, and `expected_response` of `integration.callbacks[0]`,
  and the `summary`, the `CheckMacValue` parameter `description`, and the `200`
  response `description` of the path-less webhook endpoint. The last two project to that
  webhook claim's `verification` and `expected_response`.
- The `steps` of the `CheckMacValue` crypto entry, the `when` of the four
  `field_conditions`, and the `name` of the one `test_cases` entry.
- The `type` of the seven schema fields whose table row writes the type with a space
  before the parenthesis (`String (9)`, `String (20)`, `String (1)`).

## Out of Scope

- Any change under `loop_apidoc/`. If a claim cannot be supported with the existing
  pipeline, stop and report it.
- Any source other than the derived Markdown above. On a SHA-256 mismatch, stop.
- Committing anything under `raw/`, `sources/`, or `source-quality/`.
- Changing extracted values other than the corrections listed in the Goal, and
  renaming any identifier listed in clause 4.
- `expected/minimum.json`, `expected/core-parity.json`, `source-derivation.json`, and
  the other cases without parity.
- ADR 0016 and the CI workflow.

## Acceptance Criteria

1. `uv run loop-apidoc preprocess` on `raw/gw_p110.pdf` (SHA-256 `fd12a38c…`) yields
   the Markdown that `shasum -a 256 benchmarks/ecpay-creditcard-pdf/sources/gw_p110.pdf.md`
   reports as `d42d3337d15d4c91ffad0e8efa48b294e9e1404149f20ae73b70b040cbe650b4`. The
   completion report shows both commands.
2. `uv run loop-apidoc verify-extraction --sources benchmarks/ecpay-creditcard-pdf/sources --extraction benchmarks/ecpay-creditcard-pdf/extraction`
   exits 0.
3. A script outside the repository applies the range rule to every `evidence` entry
   under `benchmarks/ecpay-creditcard-pdf/extraction/`. It prints the number of entries
   it checked and the number of violations, and the violation count is 0. The script
   and its output are in the completion report.
4. `"ecpay-creditcard-pdf"` is a member of `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES` in
   `scripts/quality_gate.py`.
5. `uv run pytest tests/test_benchmarks.py -k "ecpay" -rA` reports no failures and no
   skips, and lists `test_case_obeys_declared_core_parity_contract[ecpay-creditcard-pdf]`
   as passed.
6. A script loads each file under `benchmarks/ecpay-creditcard-pdf/extraction/` on both
   sides of `main...HEAD`, deletes every `evidence` key, and prints the remaining
   differences. Each one is a value at a location listed in the Goal's correction list.
   Its output is in the completion report.
7. `git diff --name-status main...HEAD -- benchmarks/ecpay-creditcard-pdf/expected/`
   prints nothing, or lists only `M benchmarks/ecpay-creditcard-pdf/expected/validation.expect.json`.
   In the second case, its diff changes only `current_issue_classes` counts and their
   explanatory text, and names each warning that was added or removed.
8. `benchmarks/ecpay-creditcard-pdf/notes.md` records the parity result, the range rule,
   and the corrections. The exact-evidence parity count in
   `docs/PRODUCT_EXTENSION_ROADMAP.md` and `docs/BENCHMARK_VALIDATION_PLAN.md` changes
   from 4 cases to 5 and names ECPay. The roadmap moves from "4 of 7" to "5 of 7", and
   no sentence in the roadmap still states the parity count as 4 cases.
9. `git ls-files benchmarks/ecpay-creditcard-pdf/raw benchmarks/ecpay-creditcard-pdf/sources benchmarks/ecpay-creditcard-pdf/source-quality`
   prints nothing.
10. `git diff --name-status main...HEAD` lists only files under
    `benchmarks/ecpay-creditcard-pdf/extraction/`, `benchmarks/ecpay-creditcard-pdf/notes.md`,
    `benchmarks/ecpay-creditcard-pdf/expected/validation.expect.json`,
    `scripts/quality_gate.py`, `tests/test_quality_gate.py`,
    `docs/PRODUCT_EXTENSION_ROADMAP.md`, `docs/BENCHMARK_VALIDATION_PLAN.md`, and this
    Story file (`specs/stories/ecpay-exact-evidence-parity.md`).
11. `make verify` exits 0.
