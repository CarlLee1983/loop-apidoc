# Bring apis-guru-baseline to claim-complete exact-evidence parity

## Goal

ADR 0016 makes Core graduation wait for exact-evidence parity on every restored
source-backed benchmark. Three cases meet it today, the members of
`EXACT_EVIDENCE_PARITY_BENCHMARK_CASES` in `scripts/quality_gate.py`.
`apis-guru-baseline` is the next machine-readable case. Its extraction cites one
OpenAPI YAML document. `benchmarks/apis-guru-baseline/notes.md` records that file's
immutable origin, commit `fa500d341c242326279e64402a547ff7c0717e0d`, and its SHA-256,
`dee46291d885be9ed36daabdb050e988afc5e8337760c36ad059fc440be5abb2`.

Re-acquire that exact snapshot into the gitignored `sources/` as
`apis-guru-2.2.0.openapi.yaml`, and bind every material claim in the committed
extraction to v1 `evidence[]` with exact JSON Pointer locators, as the stripe case does.
Then add the case to the exact-evidence parity lane, so
`test_case_obeys_declared_core_parity_contract` replays it.

This Story depends on `core-yaml-timestamp-fragment-digest`. Without it, binding the
`APIs` schema crashes the shadow bridge.

Some extracted values are not stated by the source, and no exact fragment can support
them. They are corrected rather than bound:

- The environment `name` `"default"` becomes `null`, because the source's `servers`
  entry has only a `url`.
- Two response descriptions, for `GET /providers.json` and `GET /{provider}/services.json`,
  become the source's `OK`. The inline-schema detail they carried is already recorded
  in `missing`.
- All five `operational` entries (`Authentication`, `Path parameters`, `License`,
  `Contact`, `External documentation`) are removed. Their topics are not source
  strings, and their details paraphrase or join several source values. The
  authentication fact moves to inventory `missing` as an entry whose text names
  authentication. That keeps `_has_auth_marker` (`loop_apidoc/validate/completeness.py`)
  satisfied for this public API.
- The `Metrics` field `datasets`, an array, is renamed `datasets[]`, the notation Core
  derives.
- The `APIs` field `{*}` and the `API` field `versions.{*}` are removed and recorded in
  their schema's `missing`. They stand for `additionalProperties` maps, which the
  pipeline cannot represent. Today the generator emits them as a literal property
  named `{*}`.

## Out of Scope

- Any change under `loop_apidoc/`. If a claim cannot be derived with the existing
  Core derivations, stop and report it rather than adding one.
- First-class `additionalProperties` (map) support in the extraction contract, plan,
  generator, or Core.
- Any source other than the exact snapshot above. On a SHA-256 mismatch, stop.
- Committing anything under `sources/` or `source-quality/`.
- Changing extracted values other than the corrections listed in the Goal.
- `expected/minimum.json`, `expected/core-parity.json`, and the other cases without
  parity.
- ADR 0016 and the CI workflow.

## Acceptance Criteria

1. `shasum -a 256 benchmarks/apis-guru-baseline/sources/apis-guru-2.2.0.openapi.yaml`
   prints `dee46291d885be9ed36daabdb050e988afc5e8337760c36ad059fc440be5abb2`. The file
   was fetched from
   `https://raw.githubusercontent.com/APIs-guru/openapi-directory/fa500d341c242326279e64402a547ff7c0717e0d/APIs/apis.guru/2.2.0/openapi.yaml`
   with `loop-apidoc snapshot-openapi-url`, and the completion report shows the command.
2. `uv run loop-apidoc verify-extraction --sources benchmarks/apis-guru-baseline/sources --extraction benchmarks/apis-guru-baseline/extraction`
   exits 0.
3. `"apis-guru-baseline"` is a member of `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES` in
   `scripts/quality_gate.py`.
4. `uv run pytest tests/test_benchmarks.py -k "apis-guru" -rA` reports no failures and
   no skips, and lists `test_case_obeys_declared_core_parity_contract[apis-guru-baseline]`
   as passed.
5. A script loads each file under `benchmarks/apis-guru-baseline/extraction/` on both
   sides of `main...HEAD`, deletes every `evidence` key, and prints the remaining
   differences. They are exactly the corrections listed in the Goal: the environment
   name, the two response descriptions, the removed `operational` entries with one
   added inventory `missing` entry, the `datasets` rename, and the two removed `{*}`
   fields with one added `missing` entry in each of their schemas. Its output is in the
   completion report.
6. `git diff --name-status main...HEAD -- benchmarks/apis-guru-baseline/expected/` lists
   only `M benchmarks/apis-guru-baseline/expected/validation.expect.json`. Its diff
   changes only `REQUIRED_INFO_MISSING.warning` from 9 to 12 and the explanatory text,
   which names the three new warnings: the empty `operational` section, and the
   success-response schema warnings for `GET /list.json` and `GET /{provider}.json`,
   whose response schema `APIs` has no representable fields.
7. `benchmarks/apis-guru-baseline/notes.md` records the parity result and each
   correction with its reason. The exact-evidence parity count in
   `docs/PRODUCT_EXTENSION_ROADMAP.md` and `docs/BENCHMARK_VALIDATION_PLAN.md` changes
   from 3 cases to 4 and names apis-guru. The roadmap moves from "3 of 7" to "4 of 7",
   and no sentence in the roadmap still states the parity count as 2 or 3 cases.
8. `git ls-files benchmarks/apis-guru-baseline/sources benchmarks/apis-guru-baseline/source-quality`
   prints nothing.
9. `git diff --name-status main...HEAD` lists only files under
   `benchmarks/apis-guru-baseline/extraction/`, `benchmarks/apis-guru-baseline/notes.md`,
   `benchmarks/apis-guru-baseline/expected/validation.expect.json`,
   `scripts/quality_gate.py`, `tests/test_quality_gate.py`,
   `docs/PRODUCT_EXTENSION_ROADMAP.md`, `docs/BENCHMARK_VALIDATION_PLAN.md`, and this
   Story file (`specs/stories/apis-guru-exact-evidence-parity.md`).
10. `make verify` exits 0.
