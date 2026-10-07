# Let the shadow bridge digest YAML fragments that contain timestamps

## Goal

The fragment adapter parses an OpenAPI YAML source with `yaml.safe_load`
(`loop_apidoc/adapters/fragments.py`, around line 380). That turns an unquoted
timestamp such as `2015-02-22 20:00:45+00:00` into a `datetime`, which ends up in a
JSON Pointer fragment's `semantic_value`. The domain serializer handles this case:
`canonical_json` in `loop_apidoc/domain/evidence.py` passes values through
`_jsonable`, which converts a `datetime` with `isoformat()`. The extraction gate and
Core verification (`_value_digest` in `loop_apidoc/core/openapi_derivation.py`) both
use that serializer.

The shadow bridge has its own serializer, `_canonical_json` in
`loop_apidoc/shadow/bridge.py` (line 647), which calls `json.dumps` directly.
`_digest_value` (line 1652) uses it to digest derivation inputs. When exact evidence
points at `/components/schemas/APIs` in the restored `apis-guru-baseline` snapshot,
whose `example` contains timestamps, the bridge raises
`TypeError: Object of type datetime is not JSON serializable`. The shadow run then
writes `core/error.json` (stage `bridge`) instead of a comparison. This was reproduced
on the snapshot with SHA-256 `dee46291d885be9ed36daabdb050e988afc5e8337760c36ad059fc440be5abb2`.

Make the bridge serialize derivation inputs exactly the way the domain serializer does,
so its digests agree with Core's. Make the domain serializer also accept a
`datetime.date`, which `yaml.safe_load` produces for a bare date such as `2015-02-22`.

## Out of Scope

- Adding `evidence[]` to any benchmark, or changing `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`.
  That belongs to the `apis-guru-exact-evidence-parity` Story.
- Changing how the fragment adapter parses YAML (for example, a loader that keeps
  timestamps as strings). That would change every existing YAML fragment digest.
- Any change to extraction digests that already verify. A fragment without a
  `date`/`datetime` must digest exactly as before.

## Acceptance Criteria

1. TDD, so the failing tests come first. A new bridge test builds a support proposal
   whose derivation input `semantic_value` contains a `datetime`. Before the change it
   fails with the `TypeError` above, and the completion report shows that red run.
   After the change it passes.
2. The input digest the bridge records for a value with a `datetime` equals
   `fragment_digest(canonical_json(value))` from `loop_apidoc/domain/evidence.py`. A
   test asserts that equality.
3. `canonical_json` in `loop_apidoc/domain/evidence.py` serializes a `datetime.date`
   with `isoformat()`, so `canonical_json({"d": date(2015, 2, 22)})` returns
   `{"d":"2015-02-22"}`. A test asserts it. Values without a `date`/`datetime`
   serialize byte-for-byte as before, and a test pins one such value's existing output.
4. `loop_apidoc/shadow/bridge.py` defines no JSON serializer of its own that bypasses
   `_jsonable`. `git grep -n "json.dumps" -- loop_apidoc/shadow/bridge.py` prints
   nothing, or each hit is named in the completion report with why it cannot receive
   a `date`/`datetime`.
5. Existing tests pass unchanged: `git diff main...HEAD -- tests/` only adds tests or
   adds cases to existing test files, with no edited assertions.
6. A reproduction outside the repository uses the apis-guru snapshot above. It binds
   v1 evidence to the `APIs` schema's `/name` claim (`/components/schemas/APIs`) in a
   scratch copy of the extraction and runs the shadow pipeline. The run produces
   `core/comparison.json` instead of `core/error.json`. The script and its output are in
   the completion report.
7. `git diff --name-status main...HEAD` lists only `loop_apidoc/shadow/bridge.py`,
   `loop_apidoc/domain/evidence.py`, test files under `tests/`, and this Story file
   (`specs/stories/core-yaml-timestamp-fragment-digest.md`).
8. `make verify` exits 0.
