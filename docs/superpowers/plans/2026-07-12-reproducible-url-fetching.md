# Reproducible URL Fetching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable, evidence-backed URL fetcher that safely captures raw HTTP responses, performs two-layer extraction, evaluates technical and semantic completeness, and fail-closes URL-backed pipeline runs unless every expected source is accepted or explicitly waived by a user.

**Architecture:** A new `loop_apidoc.urlfetch` package separates immutable models/artifacts, network policy, transport, extraction, inspection, evaluation, and coverage verification. CLI commands are thin adapters over the Python API. Existing manifest and assemble paths consume verified artifacts instead of trusting agent-written coverage declarations.

**Tech Stack:** Python 3.11+, Pydantic v2, HTTPX, Trafilatura (primary Markdown extraction), markdownify (conservative DOM-to-Markdown), pytest, Typer.

## Global Constraints

- Only public HTTP(S) destinations are allowed; every redirect hop is revalidated.
- Completed attempts are immutable and every persisted content file is SHA-256 verified.
- Obvious technical extraction failure automatically triggers conservative extraction from the same raw body.
- A semantic retry creates at most one additional HTTP attempt; identical evidence and policy cannot loop.
- URL-backed assemble runs fail closed unless every expected URL has an accepted artifact or an explicit user waiver.
- Credentials, cookies, authorization headers, proxy credentials, URL userinfo, and sensitive query values are never persisted.
- Playwright remains external; rendered HTML enters through the same artifact and evaluation boundary.

---

### Task 1: Versioned URL-fetch models and policy

**Files:**
- Create: `loop_apidoc/urlfetch/__init__.py`
- Create: `loop_apidoc/urlfetch/models.py`
- Create: `loop_apidoc/urlfetch/policy.py`
- Test: `tests/urlfetch/test_models.py`

**Interfaces:**
- Produces: `FetchRequest`, `ContentRequirements`, `FetchSignal`, `FetchMetrics`, `FetchVerdict`, `AttemptRecord`, `FetchRun`, `UrlFetchPolicy`, and enums for attempt/verdict status.

- [ ] Write tests proving unknown fields are rejected, schema version is required, sensitive query keys are configured, and retry/size/timeout defaults are finite.
- [ ] Run `uv run pytest tests/urlfetch/test_models.py -v`; expect import failure.
- [ ] Implement strict Pydantic models and immutable policy defaults.
- [ ] Re-run the test; expect PASS.
- [ ] Commit models and tests.

### Task 2: Public-network URL safety

**Files:**
- Create: `loop_apidoc/urlfetch/safety.py`
- Test: `tests/urlfetch/test_safety.py`

**Interfaces:**
- Consumes: `UrlFetchPolicy`.
- Produces: `validate_url(url: str, resolver: Resolver = ...) -> ValidatedTarget`, `redact_url(url: str, policy: UrlFetchPolicy) -> str`, `UrlSafetyError`.

- [ ] Write parameterized tests for HTTP(S), userinfo, invalid ports, IPv4/IPv6 loopback/private/link-local/reserved/multicast/unspecified, metadata IP, mixed DNS answers, IDNA hostnames, sensitive query redaction, and a redirect target becoming private.
- [ ] Run `uv run pytest tests/urlfetch/test_safety.py -v`; expect import failure.
- [ ] Implement URL parsing, resolution injection, all-address public checks, metadata denial, and redaction.
- [ ] Re-run; expect PASS.
- [ ] Commit safety implementation.

### Task 3: Bounded HTTP transport and raw response evidence

**Files:**
- Create: `loop_apidoc/urlfetch/transport.py`
- Test: `tests/urlfetch/test_transport.py`

**Interfaces:**
- Consumes: `FetchRequest`, `UrlFetchPolicy`, `validate_url`.
- Produces: `fetch_response(request, *, client_factory, resolver) -> RawFetchResult` with body bytes, safe metadata, redirect chain, truncation/error state, and SHA-256.

- [ ] Write MockTransport tests for successful streaming, byte limit, redirect loop, redirect-to-private rejection, safe-header allowlist, no cookies/auth persistence, retryable 429/5xx, and no retry on 4xx.
- [ ] Run the tests; expect missing implementation failure.
- [ ] Implement manual redirects (`follow_redirects=False`), per-hop validation, bounded streaming, finite retries/backoff injection, `trust_env=False`, and sanitized metadata.
- [ ] Re-run; expect PASS.
- [ ] Commit transport implementation.

### Task 4: Primary/conservative extraction and objective inspection

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `loop_apidoc/urlfetch/extract.py`
- Create: `loop_apidoc/urlfetch/inspect.py`
- Test: `tests/urlfetch/test_extract.py`
- Test fixtures: `tests/urlfetch/fixtures/*.html`

**Interfaces:**
- Produces: `extract_primary(html: str, url: str) -> str`, `extract_conservative(html: str) -> str`, `inspect_content(html: str, primary: str, conservative: str | None) -> FetchMetrics`, `needs_conservative(metrics) -> bool`.

- [ ] Add fixtures for article, API tables/code, SPA shell, login page, loading shell, and nav-heavy content.
- [ ] Write failing tests proving primary Markdown output, conservative table/code preservation, structural counts, and deterministic fallback signals.
- [ ] Run tests; expect missing dependencies/functions.
- [ ] Add bounded dependency floors for Trafilatura and markdownify and implement adapters/inspection without network access.
- [ ] Re-run tests and lock consistency check; expect PASS.
- [ ] Commit extraction implementation.

### Task 5: Immutable artifacts and evaluator state machine

**Files:**
- Create: `loop_apidoc/urlfetch/artifacts.py`
- Create: `loop_apidoc/urlfetch/evaluate.py`
- Create: `loop_apidoc/urlfetch/service.py`
- Test: `tests/urlfetch/test_artifacts.py`
- Test: `tests/urlfetch/test_evaluate.py`
- Test: `tests/urlfetch/test_service.py`

**Interfaces:**
- Produces: `ArtifactStore.create_attempt`, `ArtifactStore.load_run`, `ArtifactStore.verify`, `evaluate_attempt`, public `fetch_url`, and `evaluate_fetch`.

- [ ] Write failing tests for atomic creation, no overwrite, tamper detection, partial-write cleanup, accepted pointer validation, automatic conservative fallback, semantic retry budget, identical-evidence suppression, and all verdict states.
- [ ] Run tests; expect missing implementation failure.
- [ ] Implement atomic directory promotion, hash manifest, extraction orchestration, evidence-backed signals, and conservative evaluator transitions.
- [ ] Re-run; expect PASS.
- [ ] Commit artifacts/evaluator/service.

### Task 6: CLI commands and rendered import

**Files:**
- Modify: `loop_apidoc/cli.py`
- Create: `loop_apidoc/urlfetch/commands.py`
- Test: `tests/test_cli_urlfetch.py`

**Interfaces:**
- Produces CLI commands `fetch-url`, `evaluate-url`, `verify-url-sources`, `import-rendered-url`; stable `--json` payloads and distinct exit codes.

- [ ] Write Typer runner tests for command help, successful fetch, rejected URL, unresolved verdict, no-network evaluation, retry requirements, and imported rendered HTML requiring normal evaluation.
- [ ] Run tests; expect “No such command”.
- [ ] Add thin command functions, error mapping, and CLI registration.
- [ ] Re-run; expect PASS.
- [ ] Commit CLI integration.

### Task 7: Tool-generated coverage and fail-closed pipeline integration

**Files:**
- Create: `loop_apidoc/urlfetch/coverage.py`
- Modify: `loop_apidoc/manifest/models.py`
- Modify: `loop_apidoc/manifest/builder.py`
- Modify: `loop_apidoc/agentcli/assemble.py`
- Modify: `loop_apidoc/agentcli/verify.py`
- Modify: `loop_apidoc/preparation/coverage.py`
- Modify: `loop_apidoc/preparation/assess.py`
- Modify: `loop_apidoc/cli.py`
- Test: `tests/urlfetch/test_coverage.py`
- Test: `tests/test_cli_assemble.py`
- Test: `tests/agentcli/test_verify.py`

**Interfaces:**
- Produces: versioned expected/coverage artifacts, `verify_url_sources(...)`, manifest artifact references, explicit legacy-deprecation finding, and fail-closed assemble behavior.

- [ ] Write failing tests proving results cannot be self-declared, missing/unaccepted/tampered URLs exit 2, accepted files become extraction evidence, explicit waivers remain reported, manifest does not redownload when artifacts are supplied, and legacy ledgers warn without masquerading as verified.
- [ ] Run targeted tests; expect failures showing current warning-only behavior.
- [ ] Implement coverage generation/verification and thread artifact paths through manifest, verify-extraction, and assemble while preserving the declared compatibility window.
- [ ] Re-run targeted and existing URL tests; expect PASS.
- [ ] Commit pipeline integration.

### Task 8: Skill/docs migration and full verification

**Files:**
- Modify: `skills/loop-apidoc/SKILL.md`
- Modify: `skills/loop-apidoc/reference/url-fetching.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Test: `tests/test_skill_contract.py` or the existing relevant skill-contract test file.

**Interfaces:**
- Documents the exact discover → fetch-url → analyze → retry/render → verify → assemble workflow and prohibits agent-authored success results.

- [ ] Write/update contract tests asserting the new commands, artifact flow, fail-closed rule, and credential prohibition are present.
- [ ] Run the contract tests; expect failure against old SOP text.
- [ ] Update bilingual user docs and skill references.
- [ ] Run targeted tests, `uv run pytest`, `uv run ruff check .`, and package build/smoke CLI help.
- [ ] Audit every completion criterion in the design against code and test evidence; fix any uncovered gap through a new failing test first.
- [ ] Commit verified documentation and any audit fixes.
