# Extraction Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add scaffold-extraction, which projects manifest-named structured Markdown into a review-only, extraction-shaped JSON scaffold.

**Architecture:** A new loop_apidoc.extraction_scaffold package owns immutable output models, pure draft-to-scaffold projection, manifest/source collection, and its one atomic write exit. It reuses markdown_drafts collection and does not change assemble, verify-extraction, source-facts, Core shadow, or Foundry.

**Tech Stack:** Python 3.11, Pydantic v2, Typer, pytest, uv.

## Global Constraints

- Source documents remain the only authority; missing information is null or named in missing, never inferred.
- Scaffold JSON uses real extraction-contract English keys but never contains authoritative.
- A fresh scaffold directory is not a valid blessed extraction workdir: agents copy, review, and complete it first.
- write_scaffold is this feature’s sole write I/O exit; projection functions stay pure.
- Reject missing/unreadable roots, an empty usable Markdown set, and non-empty output directories before a successful output tree appears.
- Preserve endpoint order by (relative_path, start_line, method, path), with zero-padded ep<N>.json names.
- Do not project hosts, versions, security schemes, integration mechanics, statuses, tags, schema fields, or example-only nested keys.

---

### Task 1: Define scaffold models and pure projection

**Files:**

- Create: loop_apidoc/extraction_scaffold/__init__.py
- Create: loop_apidoc/extraction_scaffold/models.py
- Create: loop_apidoc/extraction_scaffold/project.py
- Test: tests/extraction_scaffold/test_project.py

**Interfaces:**

- Consumes: loop_apidoc.markdown_drafts.models.MarkdownDraftIndex.
- Produces: project_scaffold(drafts: MarkdownDraftIndex, source_texts: Mapping[str, str], sources_root_name: str) -> ScaffoldBundle.
- Produces: serializable ScaffoldBundle.inventory, ScaffoldBundle.endpoints, and ScaffoldBundle.report.

- [ ] **Step 1: Write failing projection tests for ordering and defaults**

~~~python
def test_project_scaffold_orders_endpoint_files_and_preserves_literal_fields():
    drafts = MarkdownDraftIndex(sources=(
        scan_markdown_drafts("z.md", "## POST /z\n"),
        scan_markdown_drafts("a.md", "## GET /a\n### Query\n| Name | Required |\n| --- | --- |\n| limit | yes |\n"),
    ))

    bundle = project_scaffold(drafts, {"a.md": "# A\n", "z.md": "# Z\n"}, "sources")

    assert [item.filename for item in bundle.endpoints] == ["ep00.json", "ep01.json"]
    assert bundle.inventory["version"] is None
    assert bundle.inventory["overview"] == ""
    assert bundle.endpoints[0].body["parameters"] == [{
        "name": "limit", "in": "query", "type": None, "required": True, "description": None,
    }]
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: uv run pytest tests/extraction_scaffold/test_project.py -q

Expected: FAIL during collection with ModuleNotFoundError for loop_apidoc.extraction_scaffold.

- [ ] **Step 3: Implement the minimal models and projection**

~~~python
def project_scaffold(
    drafts: MarkdownDraftIndex,
    source_texts: Mapping[str, str],
    sources_root_name: str,
) -> ScaffoldBundle:
    endpoints = sorted(
        (endpoint, source.relative_path)
        for source in drafts.sources
        for endpoint in source.endpoints
    )
    return _build_bundle(endpoints, source_texts, sources_root_name, drafts)
~~~

Implement _build_bundle to emit inventory keys title, version, overview, environments, security_schemes, endpoints, schemas, errors, operational, and missing; endpoint keys method, path, source, parameters, request, responses, tags, security, examples, and missing. Keep authoritative false in the report only.

- [ ] **Step 4: Run test to verify it passes**

Run: uv run pytest tests/extraction_scaffold/test_project.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add loop_apidoc/extraction_scaffold tests/extraction_scaffold/test_project.py
git commit -m "feat: project markdown drafts into extraction scaffold"
~~~

### Task 2: Complete fail-closed field, example, source, title, and error-table rules

**Files:**

- Modify: loop_apidoc/extraction_scaffold/project.py
- Modify: tests/extraction_scaffold/test_project.py

**Interfaces:**

- Consumes: DraftField.required, DraftExample.language, DraftExample.label, and per-source Markdown text.
- Produces: parameters[].required only for the defined required-cell matrix and missing labels for every mechanically unresolvable value or omitted example.

- [ ] **Step 1: Write failing required-value and invalid-example tests**

~~~python
@pytest.mark.parametrize(("value", "expected"), [
    ("是", True), ("必填", True), ("yes", True), ("Y", True),
    ("否", False), ("選填", False), ("no", False), ("N", False),
    ("", None), ("depends", None),
])
def test_project_scaffold_parses_only_unambiguous_required_values(value, expected):
    endpoint = _project_one_required_value(value)
    assert endpoint["parameters"][0]["required"] is expected
    assert ("required flag missing for token" in endpoint["missing"]) is (expected is None)

def test_project_scaffold_records_invalid_json_example_without_projecting_it():
    endpoint = _project("## POST /pay\n### Response\n~~~json\n{bad}\n~~~\n").endpoints[0].body
    assert endpoint["examples"] == []
    assert any("unparsed JSON example lines" in gap for gap in endpoint["missing"])
~~~

- [ ] **Step 2: Run tests to verify they fail**

Run: uv run pytest tests/extraction_scaffold/test_project.py -q

Expected: FAIL on unimplemented required parsing and missing/example behavior.

- [ ] **Step 3: Implement only the specified mechanical rules**

~~~python
def parse_required(value: str | None) -> bool | None:
    normalized = (value or "").strip().casefold()
    if normalized in {"yes", "true", "是", "必填", "y"}:
        return True
    if normalized in {"no", "false", "否", "選填", "n"}:
        return False
    return None
~~~

Map headers/query/request to header/query/body. Omit response-labelled table fields from parameters but use them for a default response. Parse only JSON-family fences with json.loads; invalid or non-JSON fences become line-ranged missing labels. Derive citations as relative_path plus lines start-end and a heading where available. Determine title only from the exactly-qualified package-entry source first H1, scan concrete hosts only outside fenced blocks, and collect numeric code plus meaning/說明 appendix rows outside endpoint sections with first-code-wins de-duplication.

- [ ] **Step 4: Run all projection tests to verify they pass**

Run: uv run pytest tests/extraction_scaffold/test_project.py -q

Expected: PASS, including required-value matrix, invalid JSON, no-host gap, title selection, and appendix errors.

- [ ] **Step 5: Commit**

~~~bash
git add loop_apidoc/extraction_scaffold/project.py tests/extraction_scaffold/test_project.py
git commit -m "feat: complete extraction scaffold projection rules"
~~~

### Task 3: Add manifest-scoped collection and atomic immutable writes

**Files:**

- Create: loop_apidoc/extraction_scaffold/collect.py
- Create: loop_apidoc/extraction_scaffold/write.py
- Create: tests/extraction_scaffold/test_collect.py
- Create: tests/extraction_scaffold/test_write.py

**Interfaces:**

- Consumes: sources_root: Path, manifest: Manifest, and output_dir: Path.
- Produces: collect_scaffold_inputs(sources_root, manifest) -> ScaffoldInputs and write_scaffold(bundle, output_dir) -> None.
- Raises: ExtractionScaffoldInputError for unreadable input/no Markdown/collision and OSError for material write failures.

- [ ] **Step 1: Write failing collection and collision tests**

~~~python
def test_collect_scaffold_inputs_rejects_manifest_with_no_readable_markdown(tmp_path: Path):
    with pytest.raises(ExtractionScaffoldInputError, match="no usable Markdown"):
        collect_scaffold_inputs(tmp_path, _manifest_with_only_ignored_sources())

def test_write_scaffold_refuses_nonempty_output_without_changing_it(tmp_path: Path):
    output = tmp_path / "scaffold"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(ExtractionScaffoldInputError, match="output already exists"):
        write_scaffold(_bundle(), output)
    assert marker.read_text(encoding="utf-8") == "keep"
~~~

- [ ] **Step 2: Run tests to verify they fail**

Run: uv run pytest tests/extraction_scaffold/test_collect.py tests/extraction_scaffold/test_write.py -q

Expected: FAIL during import because collection and write modules do not exist.

- [ ] **Step 3: Implement manifest-filtered collection and a staged write**

~~~python
def write_scaffold(bundle: ScaffoldBundle, output_dir: Path) -> None:
    _check_output_collision(output_dir)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        _write_bundle_tree(bundle, temporary)
        temporary.rename(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
~~~

Collect exactly pending Markdown manifest entries and their readable source text; reject if none are readable. Write UTF-8 JSON, the required README, and then rename the completed temporary tree into an absent or empty destination. Preserve a non-empty output unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: uv run pytest tests/extraction_scaffold/test_collect.py tests/extraction_scaffold/test_write.py -q

Expected: PASS; output contains README.md, scaffold-report.json, inventory.json, and every endpoint JSON.

- [ ] **Step 5: Commit**

~~~bash
git add loop_apidoc/extraction_scaffold tests/extraction_scaffold/test_collect.py tests/extraction_scaffold/test_write.py
git commit -m "feat: write immutable extraction scaffold output"
~~~

### Task 4: Register and test the scaffold-extraction CLI

**Files:**

- Modify: loop_apidoc/cli.py
- Create: tests/test_cli_extraction_scaffold.py

**Interfaces:**

- Consumes: loop-apidoc scaffold-extraction --sources <dir> --manifest <json> --output <dir>.
- Produces: exit 0 plus a concise JSON summary with endpoint/field/example/omitted-table counts and output; exit 2 for input, collision, and write errors.

- [ ] **Step 1: Write failing CLI success and collision tests**

~~~python
def test_scaffold_extraction_writes_review_only_tree(tmp_path: Path):
    result = runner.invoke(app, ["scaffold-extraction", "--sources", str(sources), "--manifest", str(manifest), "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["endpoints"] == 1
    assert (output / "endpoints" / "ep00.json").exists()

def test_scaffold_extraction_refuses_nonempty_output(tmp_path: Path):
    result = runner.invoke(app, ["scaffold-extraction", "--sources", str(sources), "--manifest", str(manifest), "--output", str(nonempty_output)])
    assert result.exit_code == 2
    assert "scaffold-extraction error: output already exists" in result.output
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: uv run pytest tests/test_cli_extraction_scaffold.py -q

Expected: FAIL because Typer has no scaffold-extraction command.

- [ ] **Step 3: Add the thin Typer adapter**

~~~python
@app.command(name="scaffold-extraction")
def scaffold_extraction_command(...):
    try:
        inputs = collect_scaffold_inputs(sources, load_manifest(manifest))
        bundle = project_scaffold(inputs.drafts, inputs.source_texts, sources.name)
        write_scaffold(bundle, output)
    except (ExtractionScaffoldInputError, OSError) as exc:
        typer.echo(f"scaffold-extraction error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(bundle.summary(output), ensure_ascii=False))
~~~

- [ ] **Step 4: Run feature tests and CLI help**

Run: uv run pytest tests/extraction_scaffold tests/test_cli_extraction_scaffold.py -q && uv run loop-apidoc scaffold-extraction --help

Expected: PASS; help lists the three options and review-only output.

- [ ] **Step 5: Commit**

~~~bash
git add loop_apidoc/cli.py tests/test_cli_extraction_scaffold.py
git commit -m "feat: add scaffold-extraction command"
~~~

### Task 5: Teach the review-and-copy workflow without changing authority

**Files:**

- Modify: skills/loop-apidoc/SKILL.md
- Modify: README.md
- Modify: README.en.md
- Modify: docs/index.html
- Modify: docs/introduction.html
- Modify: docs/onboarding.html
- Modify: docs/operator-manual.html
- Modify: docs/architecture-manual.html
- Modify: AGENTS.md
- Modify: CLAUDE.md
- Test: tests/test_loop_apidoc_skill.py or existing document assertions

**Interfaces:**

- Consumes: GitBook Markdown flow after manifest/drafts.
- Produces: documented examples that write to WORK/scaffold, explicitly copy inventory.json and endpoints into WORK, then review/fill gaps before verify-extraction.

- [ ] **Step 1: Write or extend a failing documentation assertion**

~~~python
def test_skill_requires_copying_scaffold_before_verification():
    text = Path("skills/loop-apidoc/SKILL.md").read_text(encoding="utf-8")
    assert "scaffold-extraction --sources" in text
    assert "WORK/scaffold is not the extraction argument" in text
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: uv run pytest tests/test_loop_apidoc_skill.py -q

Expected: FAIL because the scaffold command and non-authority statement are absent.

- [ ] **Step 3: Update English-primary guidance and synchronized teaching docs**

Add the command after the optional facts aid. State unambiguously that agents must copy into WORK, re-read citations, complete security/integration/missing items, and only then pass WORK to verification/assembly. Update command lists/package boundaries and keep AGENTS.md and CLAUDE.md aligned.

- [ ] **Step 4: Run documentation tests and focused feature regressions**

Run: uv run pytest tests/test_loop_apidoc_skill.py tests/extraction_scaffold tests/test_cli_extraction_scaffold.py -q

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add skills/loop-apidoc/SKILL.md README.md README.en.md docs/index.html docs/introduction.html docs/onboarding.html docs/operator-manual.html docs/architecture-manual.html AGENTS.md CLAUDE.md tests
git commit -m "docs: explain extraction scaffold review workflow"
~~~

### Task 6: Verify the feature against repository standards

**Files:**

- Modify: only files required to correct verification failures.

**Interfaces:**

- Consumes: all changed code, tests, and documentation.
- Produces: evidence that the new command works without changing extraction-gate semantics.

- [ ] **Step 1: Run all scaffold and adjacent draft/CLI tests**

Run: uv run pytest tests/extraction_scaffold tests/markdown_drafts tests/test_cli_extraction_scaffold.py tests/test_cli_markdown_drafts.py -q

Expected: PASS.

- [ ] **Step 2: Run the full suite and linter**

Run: uv run pytest && uv run ruff check .

Expected: all tests PASS and Ruff reports no violations.

- [ ] **Step 3: Inspect final scope compliance**

Run: git diff --check && git status --short && git diff -- loop_apidoc/agentcli loop_apidoc/source_facts loop_apidoc/shadow loop_apidoc/foundry

Expected: no whitespace errors and no unintended changes to verification, source-facts, shadow, or Foundry.

- [ ] **Step 4: Commit final verification-only corrections**

~~~bash
git add <verified-correction-files>
git commit -m "test: verify extraction scaffold workflow"
~~~

