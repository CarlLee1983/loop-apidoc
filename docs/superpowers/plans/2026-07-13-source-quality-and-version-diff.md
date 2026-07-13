# Source Quality and Version Diff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Gate API extraction on source quality, emit actionable supplement reports, and preserve source/contract differences across immutable source-set versions.

**Architecture:** Add a loop_apidoc.source_quality package with strict Pydantic contracts, pure assessment/diff functions, and JSON/Traditional-Chinese Markdown writers. A read-only agent returns source-grounded observations after preprocessing; the controller writes the JSON, and the CLI validates it with manifest facts to derive pass/reject. Existing loop-apidoc diff remains the authority for generated API contract differences.

**Tech Stack:** Python 3.11, Typer, Pydantic v2, pytest, existing manifest/preparation/diff modules.

## Global Constraints

- Preserve every prior source set, report, and API run; a supplement always creates source-set/vN+1.
- Reject exits 1 and stops before inventory.json or endpoints/*.json exist.
- No source fact may be inferred from API conventions or a file hash.
- Base accepts only the most recent source-quality pass whose run completed SPEC_REVIEW.
- Reuse existing contract-diff classification; do not reimplement OpenAPI comparison.
- Bump package and Claude plugin metadata from 0.5.0 to 0.6.0; do not publish, push, or install.

---

### Task 1: Add source-quality contracts

**Files:**
- Create: loop_apidoc/source_quality/__init__.py
- Create: loop_apidoc/source_quality/models.py
- Create: tests/source_quality/__init__.py
- Create: tests/source_quality/test_models.py

**Interfaces:**
- Produces: QualityObservation, QualityFinding, QualityVerdict, SourceQualityReport, SourceDiffEntry, and SourceDiffReport.

- [ ] **Step 1: Write failing tests**

~~~python
def test_reject_report_requires_blocker():
    report = SourceQualityReport(
        verdict=QualityVerdict.REJECT, source_set="v2", findings=[]
    )
    assert report.blocker_count == 0
~~~

Add tests rejecting observations without source, locator, or evidence; accepting actionable warnings; and preserving stable IDs such as SQ-001.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/source_quality/test_models.py -v

Expected: FAIL with missing loop_apidoc.source_quality.

- [ ] **Step 3: Implement minimal contracts**

~~~python
class QualityVerdict(str, Enum):
    PASS = "pass"
    REJECT = "reject"

class FindingSeverity(str, Enum):
    BLOCKER = "blocker"
    WARNING = "warning"

class QualityObservation(BaseModel):
    source: str
    locator: str
    category: str
    evidence: str
    severity: FindingSeverity
    affected_scope: list[str] = Field(default_factory=list)
    required_supplement: str
    acceptance_criteria: str
~~~

Keep the verdict computed by the assessor, not supplied by an observation. Include PriorFindingStatus with resolved, still_open, and regressed states and machine-readable report summaries.

- [ ] **Step 4: Verify GREEN**

Run: uv run pytest tests/source_quality/test_models.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add loop_apidoc/source_quality tests/source_quality
git commit -m "feat: add source quality report models"
~~~

### Task 2: Implement source assessment and source diff

**Files:**
- Create: loop_apidoc/source_quality/loader.py
- Create: loop_apidoc/source_quality/assess.py
- Create: loop_apidoc/source_quality/diff.py
- Create: tests/source_quality/test_assess.py
- Create: tests/source_quality/test_diff.py

**Interfaces:**
- Consumes: Manifest, observations, optional baseline manifest/report.
- Produces: assess_source_quality(...) -> SourceQualityReport and build_source_diff(...) -> SourceDiffReport.
- Raises: SourceQualityInputError for malformed or incompatible inputs.

- [ ] **Step 1: Write failing behavior tests**

~~~python
def test_no_supported_source_rejects():
    report = assess_source_quality(
        manifest=_unsupported_manifest(), source_set="v2",
        observations=[], base_report=None,
    )
    assert report.verdict is QualityVerdict.REJECT

def test_hash_change_is_source_change_not_semantic_change():
    report = build_source_diff(base=_manifest("old"), head=_manifest("new"))
    assert report.entries[0].kind == "changed"
    assert "semantic" not in report.entries[0].summary.lower()
~~~

Cover warning-only pass, observation blockers, unreadable files, file added/removed/changed, URL snapshot changes, and prior finding resolution/regression.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/source_quality/test_assess.py tests/source_quality/test_diff.py -v

Expected: FAIL because the functions and error type are absent.

- [ ] **Step 3: Implement pure assessment/diff functions**

Manifest facts classify no usable source and unreadable essential source as blockers. Observation severity is preserved only after strict validation. Compare local files by relative_path, sha256, status, and supported; compare URLs by normalized URL and content_sha256. A hash change report must say only that the source changed.

~~~python
def assess_source_quality(*, manifest, source_set, observations, base_report):
    findings = manifest_findings(manifest) + observation_findings(observations)
    return SourceQualityReport(
        verdict=QualityVerdict.REJECT if any(f.is_blocker for f in findings)
        else QualityVerdict.PASS,
        source_set=source_set,
        base_source_set=base_report.source_set if base_report else None,
        findings=findings,
        prior_findings=compare_prior_findings(base_report, findings),
    )
~~~

- [ ] **Step 4: Verify GREEN**

Run: uv run pytest tests/source_quality/test_assess.py tests/source_quality/test_diff.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add loop_apidoc/source_quality tests/source_quality
git commit -m "feat: assess source quality and source diffs"
~~~

### Task 3: Add reports and the assess-sources CLI

**Files:**
- Create: loop_apidoc/source_quality/report.py
- Modify: loop_apidoc/source_quality/__init__.py
- Modify: loop_apidoc/cli.py
- Create: tests/source_quality/test_report.py
- Create: tests/test_cli_assess_sources.py

**Interfaces:**
- Command: loop-apidoc assess-sources --sources --manifest --observations --source-set --output with optional --base-manifest and --base-report.
- Writes: source-quality-report.json, source-quality-report.zh-TW.md, source-diff.json, source-diff.md.
- Exits: 0 pass, 1 reject, 2 input/output contract error.

- [ ] **Step 1: Write failing CLI tests**

~~~python
def test_reject_writes_actionable_supplier_report(tmp_path):
    result = runner.invoke(app, [
        "assess-sources", "--sources", str(sources),
        "--manifest", str(manifest), "--observations", str(observations),
        "--source-set", "v2", "--output", str(output),
    ])
    assert result.exit_code == 1
    assert (output / "source-quality-report.json").is_file()
    assert "請補" in (output / "source-quality-report.zh-TW.md").read_text()
~~~

Cover initial pass with warnings, baseline source diff, malformed observations (2), mismatched baseline report (2), and output path as a file (2).

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/source_quality/test_report.py tests/test_cli_assess_sources.py -v

Expected: FAIL because the command and report writer are absent.

- [ ] **Step 3: Implement reports and CLI**

Render every finding with locator, affected scope, requested supplement, and acceptance criteria. Emit all four outputs for a baseline comparison; initial source sets receive an explicit empty source-diff report. Validate the manifest source root against --sources. Reject a baseline report whose verdict is not pass.

- [ ] **Step 4: Verify GREEN**

Run: uv run pytest tests/source_quality/test_report.py tests/test_cli_assess_sources.py -v

Expected: PASS, including all 0/1/2 exits and no extraction files created on reject.

- [ ] **Step 5: Commit**

~~~bash
git add loop_apidoc/source_quality loop_apidoc/cli.py tests/source_quality tests/test_cli_assess_sources.py
git commit -m "feat: add source quality gate command"
~~~

### Task 4: Insert the quality gate into the agent workflow

**Files:**
- Modify: skills/loop-apidoc/SKILL.md
- Create: skills/loop-apidoc/reference/source-quality.md
- Modify: README.md
- Modify: README.en.md
- Modify: docs/ARCHITECTURE.md
- Create: tests/test_source_quality_skill.py

**Interfaces:**
- The quality-review subagent returns only source-quality-observations.json content.
- The controller is the only writer and invokes assess-sources before inventory extraction.

- [ ] **Step 1: Write failing contract tests**

~~~python
def test_skill_places_quality_gate_before_inventory():
    text = Path("skills/loop-apidoc/SKILL.md").read_text()
    assert text.index("assess-sources") < text.index("inventory.json")
    assert "source-quality-observations.json" in text
    assert "reject" in text
~~~

Also assert the reference requires evidence-only observations, immutable source-set reruns, and sandbox trace-back through provenance, quality report, source diff, and contract diff.

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/test_source_quality_skill.py -v

Expected: FAIL because the workflow and reference are absent.

- [ ] **Step 3: Implement skill and documentation**

Document manifest -> preprocess -> quality observation -> assess-sources -> extraction. A reject stops the agent before read-only extraction fan-out. Document that a sandbox defect is first traced to artifacts, then produces a supplement request and source-set/vN+1 only when source evidence is insufficient.

- [ ] **Step 4: Verify GREEN**

Run: uv run pytest tests/test_source_quality_skill.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add skills/loop-apidoc README.md README.en.md docs/ARCHITECTURE.md tests/test_source_quality_skill.py
git commit -m "docs: add source quality gate workflow"
~~~

### Task 5: Regression validation and 0.6.0 metadata

**Files:**
- Modify: pyproject.toml
- Modify: .claude-plugin/plugin.json
- Modify: tests/test_plugin_manifest.py
- Modify: versioned README/architecture copy only where present.

- [ ] **Step 1: Write the failing version test**

~~~python
def test_package_and_plugin_versions_match_060():
    assert project_version() == "0.6.0"
    assert plugin_version() == "0.6.0"
~~~

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/test_plugin_manifest.py -v

Expected: FAIL while metadata declares 0.5.0.

- [ ] **Step 3: Update versions and run full verification**

~~~bash
uv run ruff check .
uv run pytest
uv run loop-apidoc --help
~~~

Expected: all commands exit 0 and help lists assess-sources.

- [ ] **Step 4: Run a fixture smoke test**

Create a manifest and valid observation fixture. Verify a warning-only run exits 0 and writes reports; verify a blocker exits 1 and includes a Traditional-Chinese supplement request.

- [ ] **Step 5: Commit**

~~~bash
git add pyproject.toml .claude-plugin/plugin.json README.md README.en.md docs tests
git commit -m "chore: release source quality gate 0.6.0"
~~~

## Plan self-review

- **Spec coverage:** Tasks 1–3 implement the quality gate, supplement reports, and source diffs. Task 4 puts it before extraction and records sandbox trace-back. Task 5 supplies version and regression evidence while reusing existing contract diff.
- **Placeholder scan:** Every task identifies files, concrete tests, commands, exit behavior, and interfaces.
- **Type consistency:** QualityObservation, SourceQualityReport, SourceDiffReport, SourceQualityInputError, assess_source_quality, and build_source_diff are introduced before use; CLI names and report filenames match the approved design.

