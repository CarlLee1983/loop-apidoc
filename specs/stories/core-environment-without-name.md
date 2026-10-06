# Let the Core contract represent an environment whose source states no name

## Goal

When a source states a server URL but no environment name, the extraction records the
name as `null`, as `stripe-basic-rest` now does after #179. The plan layer already
handles this case. `loop_apidoc/plan/claim_projection.py` falls back to the plan
location for the subject and omits `name` from the environment value, and the legacy
generator (`loop_apidoc/generate/openapi.py`, `_build_servers`) emits the server
without a `description`.

The Core domain model cannot represent it. `Environment.name` in
`loop_apidoc/domain/models.py` (line 44) is a required `str`. Once the server claim is
supported by exact evidence, `build_grounded_contract` calls
`Environment.model_validate` on a value with no `name`. That raises `ValidationError`,
and the shadow run fails with `core/error.json` (stage `service`). This was reproduced
on the stripe snapshot with evidence bound to the environment's server claim.

Core can graduate only when it represents every source gap without fabricating
metadata (`docs/BENCHMARK_VALIDATION_PLAN.md`). Make an environment's name optional in
the domain model, and make every Core consumer of it behave the way the legacy path
does when the name is absent.

## Out of Scope

- The extraction contract, the plan layer, `agentcli/cross_file.py`, and the legacy
  generator. They already accept a missing name.
- Inline request-body derivations and security-requirement derivations, which belong to
  the B2 and B3 Stories.
- Adding `evidence[]` to any benchmark, or changing `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`.
- Inventing a name such as the URL host or "default" for an unnamed environment.

## Acceptance Criteria

1. TDD, so the failing test comes first. A new test builds a grounded contract from a
   supported environment claim whose value has `servers` and no `name`. Before the
   change, this test fails with the `ValidationError` described in the Goal, and the
   completion report shows that red run. After the change it passes, and the
   contract's environment has `name is None` and its servers.
2. `Environment.name` in `loop_apidoc/domain/models.py` defaults to `None`. No other
   field of `Environment` changes.
3. The Core OpenAPI projection (`loop_apidoc/domain/openapi_projection.py`) emits a
   server object without a `description` key when the environment's name is `None`,
   and with `description` equal to the name otherwise. This matches `_build_servers`.
   A test covers both cases.
4. `ApiDomainRulePack.evaluate` (`loop_apidoc/domain/rules.py`) does not treat `None`
   as a resolvable environment name. An operation or binding whose `server` is unset
   behaves as before, and a test shows that a `server` reference cannot resolve
   against an unnamed environment.
5. `git grep -n 'environment\.name\|Environment(' -- loop_apidoc` lists no Core consumer
   that would fail or emit `None` for an unnamed environment. The completion report
   names each hit and why it is safe.
6. Existing tests pass unchanged: `git diff main...HEAD -- tests/` only adds tests or
   adds cases to existing test files, with no edited assertions.
7. A reproduction outside the repository uses the stripe snapshot
   (`benchmarks/stripe-basic-rest/sources/spec3.sdk.json`, SHA-256 `a58d0f7c…7fe9e`).
   It binds v1 evidence only to the environment's `/servers/<url>` claim in a scratch
   copy of the extraction and runs the shadow pipeline. The run produces
   `core/comparison.json` instead of `core/error.json`. The script and its output are in
   the completion report.
8. `git diff --name-status main...HEAD` lists only `loop_apidoc/domain/models.py`,
   `loop_apidoc/domain/openapi_projection.py`, `loop_apidoc/domain/rules.py`, test files
   under `tests/domain/`, and this Story file
   (`specs/stories/core-environment-without-name.md`).
9. `make verify` exits 0.
