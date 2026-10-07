# Bring stripe-basic-rest to claim-complete exact-evidence parity

## Goal

ADR 0016 makes Core graduation wait for exact-evidence parity on every restored
source-backed benchmark. Two cases meet it today: `funkygames-transfer-operator` and
`rsg-game-transfer-wallet`, the members of `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES` in
`scripts/quality_gate.py`. `stripe-basic-rest` is the most mechanical of the remaining
cases. Its extraction cites one machine-readable OpenAPI document,
`spec3.sdk.json`. `benchmarks/stripe-basic-rest/notes.md` records that file's immutable
origin, commit `3881db83dff8d170d4b7ef7e00e1801cd617e891`, and its SHA-256,
`a58d0f7ce76116839b2031fe1fff178283f5c686c6cdbdeaf324d6670a97fe9e`, so the same
bytes can be re-acquired and proven identical. That follows the RSG precedent of
matching hashes; it does not substitute a newer source.

Re-acquire that exact snapshot into the gitignored `sources/`, and bind every material
claim in the committed extraction to v1 `evidence[]` with exact JSON Pointer
locators, as the FunkyGames case does. Then add the case to the exact-evidence parity
lane, so `test_case_obeys_declared_core_parity_contract` replays it.

## Out of Scope

- Expanding the extraction beyond its documented Payment Intents subset (6
  operations), or changing any extracted value. Only `evidence[]` is added, with two
  approved corrections: the `payment_intent` schema field `payment_method_types` is
  renamed `payment_method_types[]` (the array notation Core derives and the extraction
  already uses for `expand[]`), and both `operational` entries are removed (their
  topics `Authentication (bearerAuth)` / `Authentication (basicAuth)` are not
  source-stated, and their details duplicate the `security_schemes` details).
- Any change under `loop_apidoc/`. If a claim cannot be derived with the existing
  Core derivations, stop and report it rather than adding one.
- Any source other than the exact snapshot above. On a SHA-256 mismatch, stop; do not
  use the newer `master` file or any other substitute.
- Committing anything under `sources/`.
- `benchmarks/stripe-basic-rest/expected/`, `core-parity.json`, and the other 10 cases
  without parity. The one exception: `expected/validation.expect.json` changes
  `REQUIRED_INFO_MISSING.warning` from 6 to 7 (the now-empty `operational` section)
  and updates its explanatory text.
- ADR 0016 and the CI workflow.

## Acceptance Criteria

1. `shasum -a 256 benchmarks/stripe-basic-rest/sources/spec3.sdk.json` prints
   `a58d0f7ce76116839b2031fe1fff178283f5c686c6cdbdeaf324d6670a97fe9e`. The file was
   fetched from
   `https://raw.githubusercontent.com/stripe/openapi/3881db83dff8d170d4b7ef7e00e1801cd617e891/openapi/spec3.sdk.json`
   through the repository's own acquisition command, and the completion report names
   the command.
2. `uv run loop-apidoc verify-extraction --sources benchmarks/stripe-basic-rest/sources --extraction benchmarks/stripe-basic-rest/extraction`
   exits 0.
3. `"stripe-basic-rest"` is a member of `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES` in
   `scripts/quality_gate.py`.
4. `uv run pytest tests/test_benchmarks.py -k "stripe" -rs` reports no failures and no
   skips, and includes `test_case_obeys_declared_core_parity_contract[stripe-basic-rest]`
   as passed. That test asserts legacy `passed`, Core `accept`, matching verdicts, and
   zero unverified claims.
5. Apart from added `evidence` entries and the two approved corrections,
   `git diff main...HEAD -- benchmarks/stripe-basic-rest/extraction/` changes no
   existing value. A script loads each file on both sides, deletes every `evidence`
   key, and compares the results; its output shows exactly two differences (the
   `payment_method_types` rename and the removed `operational` entries) and is in
   the completion report.
6. `git diff --name-status main...HEAD -- benchmarks/stripe-basic-rest/expected/`
   lists only `M benchmarks/stripe-basic-rest/expected/validation.expect.json`, whose
   diff changes only `REQUIRED_INFO_MISSING.warning` from 6 to 7 and explanatory text.
7. `benchmarks/stripe-basic-rest/notes.md` records the parity result and the two
   corrections with their reasons. The
   exact-evidence parity count in `docs/PRODUCT_EXTENSION_ROADMAP.md` and
   `docs/BENCHMARK_VALIDATION_PLAN.md` changes from 2 cases to 3 and names stripe;
   the roadmap moves from "2 of 7" to "3 of 7".
8. `git ls-files benchmarks/stripe-basic-rest/sources` prints nothing.
9. `git diff --name-status main...HEAD` lists only files under
   `benchmarks/stripe-basic-rest/extraction/`, `benchmarks/stripe-basic-rest/notes.md`,
   `benchmarks/stripe-basic-rest/expected/validation.expect.json`,
   `scripts/quality_gate.py`, `docs/PRODUCT_EXTENSION_ROADMAP.md`,
   `docs/BENCHMARK_VALIDATION_PLAN.md`, tests or docs that `make verify` requires to
   follow the parity inventory (each named and justified in the completion report), and
   this Story file (`specs/stories/stripe-exact-evidence-parity.md`).
10. `make verify` exits 0.
