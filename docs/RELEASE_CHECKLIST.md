# Release Checklist

Run before tagging a release or merging a significant pipeline change. CI
(`.github/workflows/ci.yml`) covers the deterministic checks automatically; the
items marked **(local sources)** can only run on a machine that has the
operator-provided, gitignored `benchmarks/<case>/sources/` present.

## Automated in CI

- [ ] `npm run tag:check` passes after fetching remote tags; every tag matches
  the committed SemVer `v{version}` policy and no ordering anomaly exists.
- [ ] `uv sync --dev` resolves cleanly.
- [ ] `uv run ruff check .` passes.
- [ ] `npm run docs:check` passes for the configured Markdown documents and local evidence.
- [ ] `uv run pytest --cov=loop_apidoc` passes with total coverage at or above
  the configured 92.5% floor. Do not lower this threshold without
  an explicit quality-policy decision; behavior-changing work still requires a
  focused regression test. This suite includes unit + integration + the benchmark
  discovery guard and exact-parity regression.
  - CI fails on any test failure.
  - `test_benchmark_harness_discovers_cases` proves all 13 required cases are
    still discovered even when source snapshots are absent.
  - `test_required_benchmark_cases_match_committed_cases` proves the explicit
    required inventory exactly matches the committed fixture identity files.
- [ ] `uv run python scripts/quality_gate.py` passes in CI-safe mode.
- [ ] `uv run python scripts/quality_gate.py --sanitized-fixtures` passes when
  the release changes exact-evidence materialization, Core parity, or the
  sanitized fixture contract. Report it as sanitized-fixture exact-evidence,
  never as source-backed or strict-local success.

## Benchmark harness layers

The harness has four distinct guarantees. The **13 benchmark cases** are 13
unique fixture directories, not the number of pytest test items; each case
feeds several parametrized tests.

| Layer | Release check | Guarantee |
| --- | --- | --- |
| Committed fixture inventory | Inspect `benchmarks/<case>/{extraction/inventory.json,expected/validation.expect.json}` | The case identity is committed. |
| Discovery guard | `uv run pytest tests/test_benchmarks.py -k test_benchmark_harness_discovers_cases -q` | Fixtures are enumerated without local sources. |
| Source-backed execution | `uv run pytest tests/test_benchmarks.py -q` with original snapshots present | Applicable assemble and artifact assertions execute and pass. |
| Strict-local preflight | `uv run python scripts/quality_gate.py --strict-local` | Required/committed parity, non-empty sources for every case, all checks executed, and zero skips. |

A committed or discovered case is not necessarily source-backed. A pytest
SKIP caused by a missing source snapshot is not a benchmark pass. The canonical
terminology and case-addition workflow live in
[`BENCHMARK_VALIDATION_PLAN.md`](BENCHMARK_VALIDATION_PLAN.md).

The supplemental sanitized-fixture lane is deliberately outside these four
layers. Its reviewed, line-preserving subsets give CI an exact-evidence parity
signal for retained claims, but they neither replace original snapshots nor
qualify for strict-local. `--strict-local` and `--sanitized-fixtures` are
mutually exclusive.

Implementation-backed conformance benchmarks are another distinct assurance lane. They
must report the exact Applicability Envelope, observation time, runner/suite version,
material-claim coverage, and open discrepancies. They do not increase documentary
grounding coverage and never count as source-backed or strict-local passes.

## Deep local benchmark revalidation (when source snapshots are available)

The benchmark *case* assertions in `tests/test_benchmarks.py`
(`test_benchmark_case`) **SKIP** when `benchmarks/<case>/sources/` is absent, so
CI does not exercise them. Run these checks where the original, dated source
snapshots are available:

- [ ] `uv run pytest tests/test_benchmarks.py` with sources present — every
  committed case runs (no skips) and matches its `expected/` declaration.
- [ ] Confirm all 13 benchmark cases executed and none was skipped. Do not use
  the pytest item count as the case count.
- [ ] `uv run python scripts/quality_gate.py --strict-local` passes — no
  required benchmark source directory is missing or empty, exact parity holds,
  and no benchmark check is skipped.

These checks strengthen a release but do **not** block a patch release when a
historical upstream source cannot be lawfully or reproducibly retrieved. Never
substitute a newer document or an error page just to satisfy the gate. Record
the unavailable source snapshot and perform the deterministic CI checks plus a
targeted, source-backed spot-check for the changed behavior instead.

## Manual spot-check (local sources)

Generate one representative run and eyeball the products (validation PASS does
**not** guarantee good output — read the artifacts):

- [ ] `openapi.yaml` — OpenAPI 3.1, paths/webhooks/schemas/securitySchemes as expected.
- [ ] `api-guide.zh-TW.md` — readable, complete, no placeholder leakage.
- [ ] `review.html` — open it in a browser; metrics, endpoint/schema tables, and gap list reflect the run.
- [ ] `provenance.json` — targets align 1:1 with OpenAPI locations.
- [ ] `examples/` — the three-language request examples render and wire signatures correctly.
- [ ] `integration-contract.json` — crypto/callbacks/field_conditions/test_cases match the source.
- [ ] `handoff/` — `integration-tasks.md` order/blockers read sensibly, `postman_collection.json` imports, `sdk-hints.json` covers the endpoints (derived; no schema duplicated).

## Invariant re-check

- [ ] No fabricated content: anything a source does not state stays `null` and is
  recorded in `missing`; fail-closed gaps are reported, never guessed.
- [ ] Any defect fixed in this release has a regression test, benchmark fixture,
  quality-gate scenario, or documented follow-up in `docs/PIPELINE_FOLLOWUPS.md`.
- [ ] When document preprocessing or source-risk behavior changes, exercise a supported DOCX and
  a rejected DOCX before release: confirm full-batch preflight, deterministic Markdown plus
  `.source.json` hashes/policy version, no-overwrite behavior, and exit `2` on unsafe or colliding
  input.
- [ ] Exercise `inspect-source-risk` with one warning-only source and one blocker source; confirm
  exit `0`/`1`, no payload echo, the 1,000-finding cap, and that `assess-sources`/`assemble` reject a
  stale or mismatched embedded audit before creating a run directory.
- [ ] Review `THIRD_PARTY_NOTICES.md` whenever implementation or design is adapted from another
  project; keep the upstream URL/revision, copyright, license text, and README/design attribution
  accurate.

When implementation-feedback or Effective Contract behavior changes:

- [ ] Confirm supplier sources remain the sole authority for normative/provider-documented
  claims; `confirms` and `contradicts` never alter documentary support relationships.
- [ ] Run the public `feedback assess` seam against conforming, contradictory, inconclusive,
  tampered, stale-base, unknown-claim, and scope-mismatched bundles. Confirm exit `0`/`1`/`2`,
  byte-stable reports, no network access, and rejection of output inside `.foundry`.
- [ ] Run `feedback propose`, `submit`, `review`, `approve`, `compose`, `current`, and
  `provider-erratum` at their public CLI seams. Confirm documented required flags, outputs,
  and exit `0`/`1`/`2` semantics; dry-run/handoff output must stay outside `.foundry`, and no
  feedback command may perform provider network I/O.
- [ ] Confirm proposal `--at` cannot precede the Observation Bundle's `observed_until`;
  non-approval review `--at` cannot precede observation completion and, when a proposal exists,
  cannot precede `proposal.created_at`.
- [ ] Confirm `submit` creates an explicit immutable `candidate` case with write-once inputs;
  `feedback review` accepts cases with or without proposals and records one non-approval
  decision using required reviewer identity/version, timezone-aware `--at`, disposition
  `rejected|needs_evidence`, and a corrective route other than `closed_no_change` or
  `amendment_proposal`; approval remains a separate independent-human stage that requires a
  proposal, appends write-once decision/amendment records, and creates a separate immutable
  exact-scope Effective release.
- [ ] Exercise all eight deterministic feedback routes: confirmed-only → closed; ordinary
  inconclusive → needs evidence; high-risk contradiction → provider clarification;
  harness/fixture → implementation correction; out-of-scope and DNS/proxy/gateway →
  environment correction; safe contradiction without documentary evidence → extraction
  correction; repeated network/timeout/rate-limit → provider-runtime regression review; safe
  grounded contradiction → amendment proposal.
- [ ] Confirm only confirms/contradicts count as assessed claims; inconclusive/out-of-scope
  targets remain untested/open, and unapplied contradictions increment
  `unresolved_contradiction_count`.
- [ ] Confirm observation semantic allowlisting: status/success binds the selected operation's
  response-status path; response field/type binds a matching name/type path in that operation's
  response-referenced schema. Cross-operation and mismatched paths must fail closed.
- [ ] Confirm credentials, cookies, tokens, secrets, and PII are absent from persisted fixtures
  and feedback cases. The deterministic persistence gate must reject sensitive field names and
  obvious email, phone, national-ID, SSN, passport, and Luhn-valid payment-card values; low-entropy secrets and PII must be omitted rather
  than hashed.
- [ ] Confirm the global current pointer remains normative. Effective selection must require an
  exact deployment/scope, reject conflicting active amendments, exclude expired/inapplicable
  amendments, and retain per-value authority plus full evidence/approval lineage.
- [ ] Confirm same-target active amendment conflicts fail closed unless explicit same-scope
  `--supersedes-amendment` preserves prior lineage. Confirm new normative/Effective releases
  record supersession and advance their pointer last without rewriting prior asset bytes.
- [ ] Confirm proposal and Effective composition bind the complete Normative release digest
  (contract + documentary fragments + support relationships), and reject a change to any one
  of those authority-bearing inputs.
- [ ] Confirm `feedback current` requires timezone-aware `--at`, rejects query times before
  approval/composition, expired assets, bases that are no longer normative current, and stale
  pointer/asset bindings. The pointer's `effective_asset_digest` must bind the complete
  strict-validated canonical EffectiveAsset, including all declared fields; unknown fields must
  fail closed. Asset/pointer records must also independently digest-bind, and current
  must bound, parse, digest-check, and lineage-check, `effective-contract.json`,
  `compatibility-amendment.json`, and `provenance.json`. Successful JSON must expose
  `valid_until`, `open_discrepancy_count`, `stale_amendment_count`,
  `untested_material_claim_count`, and
  `unresolved_contradiction_count`.
- [ ] Confirm governed feedback/Effective JSON rejects unknown fields, current accepts only
  `APPROVED`, and it cross-validates Effective Contract IDs/counts/validity/amendment IDs,
  approval actor/time, and provenance approval/assessment/bundle bindings.
- [ ] Confirm `stale_amendment_count` is pointer-visible and digest-bound; verifiable
  release/contract/source/policy/approval-time drift is stale, while expiry and inapplicability
  remain separate. Free-text revalidation triggers must not imply automatic execution without an
  external trigger-signal contract.
- [ ] Confirm observation/routing policy remains pure in `core/conformance_policy.py`, and all
  governed Effective lineage traversal uses `foundry.query` as its single read-side I/O.
- [ ] Confirm every Effective successor provides `supersedes` together with
  `supersedes_asset_digest`. Approval and user-facing lineage traversal must start with the same
  bound current-head read used by `feedback current`, then verify every predecessor asset digest
  and amendment artifact digest before following the next link. Explicitly superseding an
  expired lineage with a newly reviewed amendment may recover it; any historical asset metadata,
  amendment, or supersession tampering must fail before traversal and never contaminate the next
  approval/composition.
- [ ] Confirm a formal Provider Erratum re-enters source-risk → source-quality → extraction →
  verification → assembly → review → Foundry approval; no empirical shortcut may update the
  normative release.
- [ ] Review both language versions of `docs/index*`, `docs/introduction*`,
  `docs/onboarding*`, `docs/operator-manual*`, and `docs/architecture-manual*`, plus both
  READMEs, architecture, design decisions, roadmap, context/glossary, repository guidance,
  and the accepted ADR. Never describe bounded verification as universal “100% truth.”

## Completing the release publication

Prepare the release version before validation. The command requires a clean
worktree, takes the version once, synchronizes every release metadata location,
refreshes `uv.lock`, and creates a non-overwritable release-note skeleton:

```bash
# Replace <next-version> with SemVer greater than the current version.
npm run release:prepare -- --version <next-version> --summary "Describe the release"
```

Complete the notes and select exactly one `Strategy impact` option: either explain why
the release does not change product direction, priority, or subsystem scope, or list the
strategy documents updated in the same change. Review every teaching/promotion document
named in `AGENTS.md`, run the checks above, and commit the release metadata. Then use the
package's committed version instead of manually choosing a tag or creating a GitHub Release:

```bash
# Fetches origin tags first, pushes HEAD to origin/main, validates strict semver
# ordering and uniqueness, creates the annotated tag for pyproject.toml's version,
# then publishes the matching GitHub Release from docs/RELEASE_NOTES_<version>.md.
npm run release:tag -- --message "loop-apidoc <next-version>"
```

`release:tag --dry-run`, `release:tag`, and the recovery-only `release:github` reject a
missing, unresolved, or multiply selected strategy-impact declaration before auth,
fetch, push, tag, or release creation. A valid dry run then previews the tag operation
without pushing or writing a GitHub Release. A real run checks the
authenticated `gh` session with release-creation permission *before* it pushes or
creates a tag. It pushes only after Tagsmith accepts the local-and-fetched-remote
tag history; a concurrent remote tag still makes `git push` fail safely, so fetch
and retry instead of forcing a tag.

If Tagsmith has already published the tag but the final GitHub-Release step fails,
do not create the release manually. Resolve the GitHub authentication or API failure,
then run the safe recovery command from a clean worktree:

```bash
npm run release:github
```

It reads the committed package version and notes, and passes `--verify-tag` to
GitHub CLI, so GitHub cannot create a tag itself. Confirm the resulting Release URL
contains the expected title, full notes, and is neither a draft nor a prerelease.

The publication is complete only after the `main` CI run triggered by the push
passes. Record the Release URL, then identify and watch that run:

```bash
gh run list --branch main --limit 1
gh run watch <run-id> --exit-status
```

If it fails, preserve the published tag and Release, fix forward, and prepare a
new version.

### Tag authority and CI responsibilities

Tagsmith is the sole tag publisher. Use `npm run release:tag` after the local
release checks and release-metadata commit; do not create a release tag or normal
GitHub Release by hand, or expect GitHub Actions to create either. The command
pushes `HEAD` to `origin/main`, asks Tagsmith to validate and push the matching
annotated `v<package-version>` tag, then uses GitHub CLI only to publish the
matching Release after the tag exists.

GitHub Actions CI is a verification trigger only: pushes and pull requests run
tag-policy validation, dependency sync, and the quality gate. The Pages
workflow may deploy documentation from `main`, but neither workflow creates a
tag or a GitHub Release. Monitor the CI run after the push and release; a CI
failure is handled as a follow-up fix and release, never by force-moving a tag.
