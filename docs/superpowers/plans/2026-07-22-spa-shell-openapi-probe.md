# SPA-shell OpenAPI Probe and CLI Warning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Discover explicitly identifiable OpenAPI/Swagger JSON at four fixed origin-relative paths after a SPA-shell response, and warn cache operators immediately.

**Architecture:** Keep network and filesystem work in loop_apidoc.url_corpus. Add deterministic candidate and JSON-recognition helpers, then materialize accepted specifications as distinct corpus sources carrying discovery provenance. The CLI only renders the corpus-derived SPA count to stderr.

**Tech Stack:** Python 3.11, httpx, Pydantic v2, Typer, pytest.

## Global Constraints

- Probe only /swagger.json, /openapi.json, /v3/api-docs, and /api-doc/v3/sections, resolved from the SPA page origin.
- Accept only size-capped JSON objects containing a top-level openapi or swagger string; every other response writes no candidate record.
- Preserve source-grounding: accepted specifications are separate CorpusPage sources and retain their SPA-shell discovery URL(s).
- Do not add headless rendering, arbitrary probing, a dependency, or extraction/validation behavior.
- Keep network and file writes in url_corpus.py; keep candidate construction and JSON classification deterministic and unit-testable.
- Human-facing documentation is English-primary with Traditional-Chinese supporting copy; update release-required documents whose command descriptions would otherwise be incomplete.

---

### Task 1: Define the discovery contract and test it first

**Files:**
- Modify: loop_apidoc/url_corpus.py:16-57,115-191
- Modify: tests/test_cli_url_corpus.py:12-195

**Interfaces:**
- Produces: openapi_spec_candidates(page_url: str) -> list[str]
- Produces: recognized_spec_kind(raw: bytes, encoding: str | None) -> Literal["openapi", "swagger"] | None
- Produces: CorpusPage.source_kind: Literal["document", "openapi_spec"] and CorpusPage.discovered_from: list[str]

- [ ] **Step 1: Write the failing tests**

~~~python
def test_openapi_spec_candidates_use_only_the_page_origin():
    assert openapi_spec_candidates("https://docs.example.com/guides/intro?lang=en") == [
        "https://docs.example.com/swagger.json",
        "https://docs.example.com/openapi.json",
        "https://docs.example.com/v3/api-docs",
        "https://docs.example.com/api-doc/v3/sections",
    ]


def test_recognized_spec_kind_requires_an_openapi_or_swagger_root_field():
    assert recognized_spec_kind(b'{"openapi":"3.1.0"}', "utf-8") == "openapi"
    assert recognized_spec_kind(b'{"swagger":"2.0"}', "utf-8") == "swagger"
    assert recognized_spec_kind(b'{"status":"ok"}', "utf-8") is None
    assert recognized_spec_kind(b"not json", "utf-8") is None
~~~

- [ ] **Step 2: Run the tests to verify failure**

Run: uv run pytest tests/test_cli_url_corpus.py -k 'openapi_spec_candidates or recognized_spec_kind' -v

Expected: FAIL during collection because the helpers do not exist.

- [ ] **Step 3: Implement the minimum deterministic contract**

~~~python
_OPENAPI_SPEC_PATHS = ("/swagger.json", "/openapi.json", "/v3/api-docs", "/api-doc/v3/sections")


def openapi_spec_candidates(page_url: str) -> list[str]:
    parts = urlsplit(page_url)
    origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    return [urljoin(origin, path) for path in _OPENAPI_SPEC_PATHS]


def recognized_spec_kind(raw: bytes, encoding: str | None) -> Literal["openapi", "swagger"] | None:
    try:
        document = json.loads(raw.decode(encoding or "utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict):
        return None
    for key in ("openapi", "swagger"):
        if isinstance(document.get(key), str):
            return key
    return None
~~~

Add source_kind (default "document") and discovered_from (empty-list factory) to CorpusPage; import json and urllib.parse helpers.

- [ ] **Step 4: Run the focused tests to verify pass**

Run: uv run pytest tests/test_cli_url_corpus.py -k 'openapi_spec_candidates or recognized_spec_kind' -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add loop_apidoc/url_corpus.py tests/test_cli_url_corpus.py
git commit -m "feat: define SPA OpenAPI probe contract"
~~~

### Task 2: Cache accepted probes as independent sources

**Files:**
- Modify: loop_apidoc/url_corpus.py:191-294
- Modify: tests/test_cli_url_corpus.py:153-195

**Interfaces:**
- Consumes: both Task 1 helpers.
- Produces: cache_catalog_pages(...) -> UrlCorpus pages with source_kind="openapi_spec", a .json raw file, and discovery provenance.

- [ ] **Step 1: Write failing HTTP cache-flow tests**

~~~python
def test_spa_shell_caches_a_recognized_openapi_document_as_a_distinct_source(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/page":
            return httpx.Response(200, text=_SHELL_HTML)
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json={"openapi": "3.1.0"})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        corpus = cache_catalog_pages(
            UrlCatalog(
                entry_url="https://docs.example.com/page",
                nodes=[CatalogNode(url="https://docs.example.com/page", title="Doc")],
            ),
            tmp_path,
            client=client,
        )

    spec = next(page for page in corpus.pages if page.source_kind == "openapi_spec")
    assert spec.url == "https://docs.example.com/openapi.json"
    assert spec.discovered_from == ["https://docs.example.com/page"]
    assert spec.raw_file and spec.raw_file.endswith(".json")
~~~

Add tests where all candidates are 404 or generic JSON and assert only the document page remains. Add two SPA shells at one origin and assert each candidate is requested once; an accepted page lists both shell URLs in encounter order.

- [ ] **Step 2: Run tests to verify failure**

Run: uv run pytest tests/test_cli_url_corpus.py -k 'caches_a_recognized_openapi or non_spec_json or deduplicates' -v

Expected: FAIL because no probe is performed.

- [ ] **Step 3: Implement bounded fail-closed probing**

~~~python
def _probe_openapi_specs(
    active_client: httpx.Client,
    shell_urls: list[str],
    output_dir: Path,
    max_bytes_per_page: int,
) -> list[CorpusPage]:
    origins_by_candidate: dict[str, list[str]] = {}
    for shell_url in shell_urls:
        for candidate in openapi_spec_candidates(shell_url):
            origins_by_candidate.setdefault(candidate, []).append(shell_url)

    pages: list[CorpusPage] = []
    for candidate, origins in origins_by_candidate.items():
        try:
            with active_client.stream("GET", candidate, headers={"Accept": "application/json"}) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes_per_page:
                        raise ValueError(f"response exceeds {max_bytes_per_page} byte cap")
                    chunks.append(chunk)
                raw = b"".join(chunks)
        except (httpx.HTTPError, ValueError):
            continue
        encoding = response.encoding or "utf-8"
        if recognized_spec_kind(raw, encoding) is None:
            continue
        text = raw.decode(encoding)
        digest = hashlib.sha256(raw).hexdigest()
        raw_relative = Path("raw") / f"{digest}.json"
        body_relative = Path("body") / f"{digest}.txt"
        (output_dir / raw_relative).write_bytes(raw) if not (output_dir / raw_relative).exists() else None
        (output_dir / body_relative).write_text(text, encoding="utf-8") if not (output_dir / body_relative).exists() else None
        pages.append(CorpusPage(
            url=candidate, status="fetched", raw_file=raw_relative.as_posix(),
            body_file=body_relative.as_posix(), content_sha256=digest,
            byte_size=len(raw), body_characters=len(text), source_kind="openapi_spec",
            discovered_from=origins,
        ))
    return pages
~~~

Collect shell URLs while caching catalog documents, then extend pages with this helper before returning the corpus. Persist accepted JSON as raw/<sha256>.json and body/<sha256>.txt only if absent. Send Accept: application/json; do not create fetch_failed pages for probes.

- [ ] **Step 4: Run tests to verify pass**

Run: uv run pytest tests/test_cli_url_corpus.py -k 'spa_shell or openapi or deduplicates' -v

Expected: PASS, including existing shell-detection tests.

- [ ] **Step 5: Commit**

~~~bash
git add loop_apidoc/url_corpus.py tests/test_cli_url_corpus.py
git commit -m "feat: cache OpenAPI specs discovered from SPA shells"
~~~

### Task 3: Emit a consistent CLI warning

**Files:**
- Modify: loop_apidoc/cli.py:152-216
- Modify: tests/test_cli_url_corpus.py:18-103

**Interfaces:**
- Consumes: UrlCorpus.pages and CorpusPage.source_kind / spa_shell_detected.
- Produces: _emit_spa_shell_warning(corpus: UrlCorpus) -> None.

- [ ] **Step 1: Write failing command tests**

~~~python
def test_cache_url_pages_warns_on_detected_spa_shell(tmp_path: Path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        UrlCatalog(
            entry_url="https://docs.example.com/intro",
            nodes=[CatalogNode(url="https://docs.example.com/intro", title="Intro")],
        ).model_dump_json(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "loop_apidoc.url_corpus.cache_catalog_pages",
        lambda *_args, **_kwargs: UrlCorpus(
            entry_url="https://docs.example.com/intro",
            pages=[
                CorpusPage(url="https://docs.example.com/intro", status="fetched", spa_shell_detected=True),
                CorpusPage(url="https://docs.example.com/openapi.json", status="fetched", source_kind="openapi_spec"),
            ],
        ),
    )
    result = runner.invoke(app, ["cache-url-pages", "--catalog", str(catalog_path), "--output", str(tmp_path / "out")])
    assert result.exit_code == 0
    assert "1/1 pages look like un-rendered SPA shells" in result.stderr
~~~

Add equivalent cache-url-entry and no-shell tests.

- [ ] **Step 2: Run tests to verify failure**

Run: uv run pytest tests/test_cli_url_corpus.py -k 'warns_on_detected_spa_shell or no_shell' -v

Expected: FAIL because no command writes this warning.

- [ ] **Step 3: Implement one shared formatter**

~~~python
def _emit_spa_shell_warning(corpus: UrlCorpus) -> None:
    documents = [page for page in corpus.pages if page.source_kind == "document"]
    shells = sum(page.spa_shell_detected for page in documents)
    if shells:
        typer.echo(f"{shells}/{len(documents)} pages look like un-rendered SPA shells", err=True)
~~~

Call it after corpus.json is written in both cache commands and before their normal success output.

- [ ] **Step 4: Run CLI tests to verify pass**

Run: uv run pytest tests/test_cli_url_corpus.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add loop_apidoc/cli.py tests/test_cli_url_corpus.py
git commit -m "feat: warn when URL cache detects SPA shells"
~~~

### Task 4: Synchronize the operator documentation

**Files:**
- Modify: README.en.md:217-237
- Modify: README.md:209-229
- Modify: docs/operator-manual.html:171-185
- Modify: docs/architecture-manual.html:730-823
- Modify: docs/onboarding.html:776-780
- Modify if needed after review: AGENTS.md, CLAUDE.md
- Review: docs/index.html, docs/introduction.html

**Interfaces:**
- Consumes: final Tasks 2-3 behavior.
- Produces: accurate English-primary and zh-TW supporting guidance for accepted sources and the operator warning.

- [ ] **Step 1: Update README text**

Add this paragraph to README.en.md after the URL corpus explanation:

~~~markdown
If a cached HTML page is an un-rendered SPA shell, loop-apidoc probes only four fixed origin-relative paths for JSON documents with an openapi or swagger root field. Accepted specifications are stored as separate corpus sources; failed or non-spec responses are not recorded. The command reports the number of detected shells on stderr.
~~~

Add matching Traditional-Chinese copy to README.md, including that generic JSON is not accepted.

- [ ] **Step 2: Update and review release-required HTML and agent documentation**

Add concise matching zh-TW guidance to the URL-corpus sections of the operator manual, architecture manual, and onboarding. Verify docs/index.html and docs/introduction.html contain no detailed command claim requiring a change. Update AGENTS.md and CLAUDE.md identically if their url_corpus.py summary omits the new probe.

- [ ] **Step 3: Verify documentation**

Run: rg -n 'swagger.json|openapi.json|un-rendered SPA|SPA shell' README.en.md README.md docs/operator-manual.html docs/architecture-manual.html docs/onboarding.html AGENTS.md CLAUDE.md

Expected: guidance describes fixed paths, root-field validation, separate sources, and stderr warnings; it does not imply automatic headless rendering.

- [ ] **Step 4: Commit**

~~~bash
git add README.en.md README.md docs/operator-manual.html docs/architecture-manual.html docs/onboarding.html AGENTS.md CLAUDE.md
git commit -m "docs: describe SPA shell OpenAPI probing"
~~~

### Task 5: Verify and complete issue follow-up

**Files:**
- Verify: loop_apidoc/url_corpus.py, loop_apidoc/cli.py, tests/test_cli_url_corpus.py

**Interfaces:**
- Consumes: all preceding tasks.
- Produces: evidence that #22 is complete and an issue-resolution comment ready for user authorization.

- [ ] **Step 1: Run focused regression tests**

Run: uv run pytest tests/test_cli_url_corpus.py tests/url_corpus/test_cache.py tests/url_corpus/test_relations.py -v

Expected: PASS.

- [ ] **Step 2: Run project checks**

Run: uv run ruff check loop_apidoc tests

Expected: All checks passed!

Run: uv run pytest

Expected: PASS with no failures.

- [ ] **Step 3: Inspect final state**

Run: git diff HEAD~4..HEAD --check

Expected: no output.

Run: git status --short

Expected: empty output.

- [ ] **Step 4: Obtain authorization before writing on GitHub**

Prepare this comment, restate it and issue #22 to the user before posting:

~~~markdown
Implemented SPA-shell OpenAPI/Swagger probing and CLI warnings. The cache now probes only the four documented origin-relative paths, records only JSON with an openapi or swagger root as a separate source, leaves failed/non-spec probes unrecorded, and reports detected shell counts on stderr. Focused tests, lint, and the full test suite pass.
~~~

Use gh issue comment 22 --body ... only after that authorization. Close the issue only if the user explicitly requests closure.
