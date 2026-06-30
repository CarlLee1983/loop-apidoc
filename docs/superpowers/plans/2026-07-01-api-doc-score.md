# API Documentation Score Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic API documentation score reports for completed `loop-apidoc` run directories and optionally write them from `assemble --score`.

**Architecture:** Add a focused `loop_apidoc.score` package with Pydantic report models, a run-dir loader, a pure evaluator, and report writers. Wire a new Typer `score` command and a narrow `assemble --score` option over the package without changing validation semantics.

**Tech Stack:** Python 3.11, Typer, Pydantic v2, PyYAML, pytest, existing `loop_apidoc.validate`, `manifest`, and `generate` models.

---

## File Structure

- Create `loop_apidoc/score/models.py`: score enums, report models, input dataclass, default thresholds, category weights, and `ScoreInputError`.
- Create `loop_apidoc/score/loader.py`: load required run-dir artifacts into `ScoreInputs` and raise deterministic file-named input errors.
- Create `loop_apidoc/score/evaluate.py`: pure scoring logic, issue-to-category mapping, category penalties, profile-specific blocking rules, and status selection.
- Create `loop_apidoc/score/report.py`: render `score.md` and write `score/score.json` plus `score/score.md`.
- Create `loop_apidoc/score/__init__.py`: public exports used by CLI and tests.
- Modify `loop_apidoc/cli.py`: add `score` command and `assemble --score` wiring.
- Modify `README.md`: document score command and output directory.
- Modify `docs/ARCHITECTURE.md`: add score package to package boundary and data-flow references.
- Create `tests/score/test_models.py`: report contract and threshold tests.
- Create `tests/score/test_loader.py`: required artifact parsing and input-error tests.
- Create `tests/score/test_evaluate.py`: category scoring, profile behavior, and status tests.
- Create `tests/score/test_report.py`: Markdown and file writer tests.
- Create `tests/test_cli_score.py`: `score` command exit-code, JSON, and output tests.
- Modify `tests/test_cli_assemble.py`: assert `assemble --score` writes score reports and returns the original assemble status.

## Task 1: Score Models

**Files:**
- Create: `loop_apidoc/score/__init__.py`
- Create: `loop_apidoc/score/models.py`
- Create: `tests/score/__init__.py`
- Create: `tests/score/test_models.py`

- [ ] **Step 1: Write model contract tests**

Create `tests/score/__init__.py` as an empty file.

Create `tests/score/test_models.py`:

```python
from __future__ import annotations

from loop_apidoc.score.models import (
    CATEGORY_WEIGHTS,
    DEFAULT_MIN_SCORES,
    ScoreCategory,
    ScoreFinding,
    ScoreProfile,
    ScoreReport,
    ScoreStatus,
    resolved_min_score,
)


def test_category_weights_sum_to_100() -> None:
    assert sum(CATEGORY_WEIGHTS.values()) == 100
    assert set(CATEGORY_WEIGHTS) == {category.value for category in ScoreCategory}


def test_resolved_min_score_uses_profile_default_or_override() -> None:
    assert DEFAULT_MIN_SCORES[ScoreProfile.CI] == 85
    assert DEFAULT_MIN_SCORES[ScoreProfile.REVIEW] == 70
    assert resolved_min_score(ScoreProfile.CI, None) == 85
    assert resolved_min_score(ScoreProfile.REVIEW, 63) == 63


def test_score_report_serializes_stable_json_keys() -> None:
    finding = ScoreFinding(
        code="REQUIRED_INFO_MISSING",
        severity="warning",
        location="paths./ping.get.responses",
        evidence="response example absent",
        suggested_fix="Re-read endpoint source and add the missing response example.",
        category=ScoreCategory.COMPLETENESS,
        blocking=False,
        score_impact=12,
    )
    report = ScoreReport(
        status=ScoreStatus.NEEDS_ATTENTION,
        score=88,
        profile=ScoreProfile.CI,
        min_score=85,
        category_scores={
            "openapi_validity": 100,
            "completeness": 88,
            "consistency": 100,
            "source_grounding": 100,
            "reviewability": 100,
        },
        blocking_findings=[],
        findings=[finding],
    )

    payload = report.model_dump(mode="json")

    assert payload["status"] == "needs_attention"
    assert payload["profile"] == "ci"
    assert payload["category_scores"]["completeness"] == 88
    assert payload["findings"][0]["category"] == "completeness"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/score/test_models.py -v
```

Expected: FAIL during import with `ModuleNotFoundError: No module named 'loop_apidoc.score'`.

- [ ] **Step 3: Add score model package**

Create `loop_apidoc/score/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.validate.models import ValidationReport


class ScoreStatus(str, Enum):
    PASS = "pass"
    NEEDS_ATTENTION = "needs_attention"
    FAIL = "fail"


class ScoreProfile(str, Enum):
    CI = "ci"
    REVIEW = "review"


class ScoreCategory(str, Enum):
    OPENAPI_VALIDITY = "openapi_validity"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    SOURCE_GROUNDING = "source_grounding"
    REVIEWABILITY = "reviewability"


CATEGORY_WEIGHTS: dict[str, int] = {
    ScoreCategory.OPENAPI_VALIDITY.value: 20,
    ScoreCategory.COMPLETENESS.value: 30,
    ScoreCategory.CONSISTENCY.value: 20,
    ScoreCategory.SOURCE_GROUNDING.value: 20,
    ScoreCategory.REVIEWABILITY.value: 10,
}

DEFAULT_MIN_SCORES: dict[ScoreProfile, int] = {
    ScoreProfile.CI: 85,
    ScoreProfile.REVIEW: 70,
}


class ScoreInputError(ValueError):
    """The run directory cannot be scored because an artifact is missing or invalid."""


class ScoreFinding(BaseModel):
    code: str
    severity: str
    location: str
    evidence: str
    suggested_fix: str
    category: ScoreCategory
    blocking: bool
    score_impact: int = Field(ge=0, le=100)


class ScoreReport(BaseModel):
    status: ScoreStatus
    score: int = Field(ge=0, le=100)
    profile: ScoreProfile
    min_score: int = Field(ge=0, le=100)
    category_scores: dict[str, int]
    blocking_findings: list[ScoreFinding] = Field(default_factory=list)
    findings: list[ScoreFinding] = Field(default_factory=list)


@dataclass(frozen=True)
class ScoreInputs:
    run_dir: Path
    openapi: dict
    validation: ValidationReport
    provenance: ProvenanceDocument
    manifest: Manifest
    plan: dict | None = None
    review_html_exists: bool = False
    validation_markdown_exists: bool = False


def resolved_min_score(profile: ScoreProfile, explicit_min_score: int | None) -> int:
    return DEFAULT_MIN_SCORES[profile] if explicit_min_score is None else explicit_min_score
```

Create `loop_apidoc/score/__init__.py`:

```python
"""Score reports for completed loop-apidoc run directories."""

from loop_apidoc.score.models import (
    CATEGORY_WEIGHTS,
    DEFAULT_MIN_SCORES,
    ScoreCategory,
    ScoreFinding,
    ScoreInputError,
    ScoreInputs,
    ScoreProfile,
    ScoreReport,
    ScoreStatus,
    resolved_min_score,
)

__all__ = [
    "CATEGORY_WEIGHTS",
    "DEFAULT_MIN_SCORES",
    "ScoreCategory",
    "ScoreFinding",
    "ScoreInputError",
    "ScoreInputs",
    "ScoreProfile",
    "ScoreReport",
    "ScoreStatus",
    "resolved_min_score",
]
```

- [ ] **Step 4: Run model tests**

Run:

```bash
uv run pytest tests/score/test_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add loop_apidoc/score/__init__.py loop_apidoc/score/models.py tests/score/__init__.py tests/score/test_models.py
git commit -m "Define the API documentation score report contract" -m "Create the score report models and defaults before adding loaders or evaluators.

Constraint: Reports must serialize stable string keys for CI and agent consumers.
Confidence: high
Scope-risk: narrow
Directive: Keep scoring models deterministic and independent from source re-reading.
Tested: uv run pytest tests/score/test_models.py -v
Not-tested: Loader, evaluator, CLI, and assemble integration are not implemented in this task."
```

## Task 2: Run Directory Loader

**Files:**
- Modify: `loop_apidoc/score/__init__.py`
- Create: `loop_apidoc/score/loader.py`
- Create: `tests/score/test_loader.py`

- [ ] **Step 1: Write loader tests**

Create `tests/score/test_loader.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.score.loader import load_score_inputs
from loop_apidoc.score.models import ScoreInputError
from loop_apidoc.validate.models import ValidationReport

_NOW = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "paths": {"/ping": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }


def write_score_run(run_dir: Path, *, include_plan: bool = True) -> Path:
    run_dir.mkdir(parents=True)
    (run_dir / "openapi.yaml").write_text(
        yaml.safe_dump(_openapi(), sort_keys=False),
        encoding="utf-8",
    )
    provenance = ProvenanceDocument(
        notebook_url="",
        entries=[
            ProvenanceEntry(
                target="paths./ping.get",
                status=PlanItemStatus.SUPPORTED,
                manifest_source="manual.md",
                query_id="06",
                answer_path="answers/06.txt",
                locator="p.1",
            )
        ],
    )
    (run_dir / "provenance.json").write_text(
        provenance.model_dump_json(indent=2),
        encoding="utf-8",
    )
    validation_dir = run_dir / "validation"
    validation_dir.mkdir()
    (validation_dir / "report.json").write_text(
        ValidationReport().model_dump_json(indent=2),
        encoding="utf-8",
    )
    (validation_dir / "report.md").write_text("# Validation\n", encoding="utf-8")
    manifest = Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=10,
                sha256="abc",
                scanned_at=_NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )
    if include_plan:
        (run_dir / "plan").mkdir()
        (run_dir / "plan" / "normalization-plan.json").write_text(
            json.dumps({"endpoints": [{"path": "/ping"}]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (run_dir / "review.html").write_text("<html></html>", encoding="utf-8")
    return run_dir


def test_load_score_inputs_reads_required_and_optional_artifacts(tmp_path: Path) -> None:
    run_dir = write_score_run(tmp_path / "run")

    inputs = load_score_inputs(run_dir)

    assert inputs.run_dir == run_dir
    assert inputs.openapi["info"]["title"] == "Demo"
    assert inputs.validation.ok is True
    assert inputs.provenance.entries[0].target == "paths./ping.get"
    assert inputs.manifest.local_sources[0].relative_path == "manual.md"
    assert inputs.plan == {"endpoints": [{"path": "/ping"}]}
    assert inputs.review_html_exists is True
    assert inputs.validation_markdown_exists is True


def test_load_score_inputs_allows_missing_plan(tmp_path: Path) -> None:
    inputs = load_score_inputs(write_score_run(tmp_path / "run", include_plan=False))
    assert inputs.plan is None


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("openapi.yaml", "openapi.yaml"),
        ("provenance.json", "provenance.json"),
        ("validation/report.json", "validation/report.json"),
        ("manifest.json", "manifest.json"),
    ],
)
def test_load_score_inputs_rejects_missing_required_file(
    tmp_path: Path,
    relative_path: str,
    message: str,
) -> None:
    run_dir = write_score_run(tmp_path / "run")
    (run_dir / relative_path).unlink()

    with pytest.raises(ScoreInputError) as excinfo:
        load_score_inputs(run_dir)

    assert message in str(excinfo.value)


def test_load_score_inputs_rejects_invalid_openapi_yaml(tmp_path: Path) -> None:
    run_dir = write_score_run(tmp_path / "run")
    (run_dir / "openapi.yaml").write_text("a: b:\n  - broken", encoding="utf-8")

    with pytest.raises(ScoreInputError) as excinfo:
        load_score_inputs(run_dir)

    assert "openapi.yaml" in str(excinfo.value)


@pytest.mark.parametrize(
    "relative_path",
    ["provenance.json", "validation/report.json", "manifest.json"],
)
def test_load_score_inputs_schema_error_names_file(
    tmp_path: Path,
    relative_path: str,
) -> None:
    run_dir = write_score_run(tmp_path / "run")
    (run_dir / relative_path).write_text("123", encoding="utf-8")

    with pytest.raises(ScoreInputError) as excinfo:
        load_score_inputs(run_dir)

    assert relative_path in str(excinfo.value)


def test_load_score_inputs_invalid_optional_plan_names_file(tmp_path: Path) -> None:
    run_dir = write_score_run(tmp_path / "run")
    (run_dir / "plan" / "normalization-plan.json").write_text("{", encoding="utf-8")

    with pytest.raises(ScoreInputError) as excinfo:
        load_score_inputs(run_dir)

    assert "plan/normalization-plan.json" in str(excinfo.value)
```

- [ ] **Step 2: Run loader tests to verify they fail**

Run:

```bash
uv run pytest tests/score/test_loader.py -v
```

Expected: FAIL during import with `ModuleNotFoundError: No module named 'loop_apidoc.score.loader'`.

- [ ] **Step 3: Add loader implementation**

Create `loop_apidoc/score/loader.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.score.models import ScoreInputError, ScoreInputs
from loop_apidoc.validate.models import ValidationReport

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ScoreInputError(f"required artifact missing: {label}")


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScoreInputError(f"cannot read {label}: {str(exc)[:200]}") from exc


def _validate_model(model: type[_ModelT], path: Path, label: str) -> _ModelT:
    try:
        return model.model_validate_json(_read_text(path, label))
    except ValidationError as exc:
        raise ScoreInputError(f"{label} schema mismatch: {str(exc)[:200]}") from exc


def _load_json_object(path: Path, label: str) -> dict:
    try:
        loaded = json.loads(_read_text(path, label))
    except json.JSONDecodeError as exc:
        raise ScoreInputError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ScoreInputError(f"{label} must be a JSON object")
    return loaded


def load_score_inputs(run_dir: Path) -> ScoreInputs:
    if not run_dir.is_dir():
        raise ScoreInputError(f"run directory does not exist: {run_dir}")

    openapi_path = run_dir / "openapi.yaml"
    provenance_path = run_dir / "provenance.json"
    validation_path = run_dir / "validation" / "report.json"
    manifest_path = run_dir / "manifest.json"
    plan_path = run_dir / "plan" / "normalization-plan.json"

    for path, label in (
        (openapi_path, "openapi.yaml"),
        (provenance_path, "provenance.json"),
        (validation_path, "validation/report.json"),
        (manifest_path, "manifest.json"),
    ):
        _require_file(path, label)

    try:
        openapi = yaml.safe_load(_read_text(openapi_path, "openapi.yaml"))
    except yaml.YAMLError as exc:
        raise ScoreInputError(f"openapi.yaml is not valid YAML: {exc}") from exc
    if not isinstance(openapi, dict):
        raise ScoreInputError("openapi.yaml must parse to an object")

    plan = None
    if plan_path.exists():
        plan = _load_json_object(plan_path, "plan/normalization-plan.json")

    return ScoreInputs(
        run_dir=run_dir,
        openapi=openapi,
        validation=_validate_model(
            ValidationReport,
            validation_path,
            "validation/report.json",
        ),
        provenance=_validate_model(ProvenanceDocument, provenance_path, "provenance.json"),
        manifest=_validate_model(Manifest, manifest_path, "manifest.json"),
        plan=plan,
        review_html_exists=(run_dir / "review.html").is_file(),
        validation_markdown_exists=(run_dir / "validation" / "report.md").is_file(),
    )
```

Update `loop_apidoc/score/__init__.py`:

```python
"""Score reports for completed loop-apidoc run directories."""

from loop_apidoc.score.loader import load_score_inputs
from loop_apidoc.score.models import (
    CATEGORY_WEIGHTS,
    DEFAULT_MIN_SCORES,
    ScoreCategory,
    ScoreFinding,
    ScoreInputError,
    ScoreInputs,
    ScoreProfile,
    ScoreReport,
    ScoreStatus,
    resolved_min_score,
)

__all__ = [
    "CATEGORY_WEIGHTS",
    "DEFAULT_MIN_SCORES",
    "ScoreCategory",
    "ScoreFinding",
    "ScoreInputError",
    "ScoreInputs",
    "ScoreProfile",
    "ScoreReport",
    "ScoreStatus",
    "load_score_inputs",
    "resolved_min_score",
]
```

- [ ] **Step 4: Run loader tests**

Run:

```bash
uv run pytest tests/score/test_loader.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add loop_apidoc/score/__init__.py loop_apidoc/score/loader.py tests/score/test_loader.py
git commit -m "Load score inputs from completed run directories" -m "Add deterministic artifact loading for score reports.

Constraint: Score reads completed run artifacts only and fails loudly on missing or invalid inputs.
Confidence: high
Scope-risk: narrow
Directive: Keep loader errors file-named so CI and agents can repair the right artifact.
Tested: uv run pytest tests/score/test_loader.py -v
Not-tested: Scoring math, reports, and CLI wiring are not implemented in this task."
```

## Task 3: Score Evaluator

**Files:**
- Modify: `loop_apidoc/score/__init__.py`
- Create: `loop_apidoc/score/evaluate.py`
- Create: `tests/score/test_evaluate.py`

- [ ] **Step 1: Write evaluator tests**

Create `tests/score/test_evaluate.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.score.evaluate import evaluate_score
from loop_apidoc.score.models import ScoreCategory, ScoreInputs, ScoreProfile, ScoreStatus
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport

_NOW = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)


def _manifest(*, status: ProcessingStatus = ProcessingStatus.PENDING) -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=10,
                sha256="abc",
                scanned_at=_NOW,
                supported=(status is ProcessingStatus.PENDING),
                status=status,
            )
        ],
    )


def _inputs(
    issues: list[Issue] | None = None,
    *,
    run_dir: Path = Path("output/run"),
    review_html_exists: bool = True,
    validation_markdown_exists: bool = True,
    manifest: Manifest | None = None,
) -> ScoreInputs:
    return ScoreInputs(
        run_dir=run_dir,
        openapi={"openapi": "3.1.0", "info": {"title": "Demo"}, "paths": {}},
        validation=ValidationReport(issues=issues or []),
        provenance=ProvenanceDocument(notebook_url="", entries=[]),
        manifest=manifest or _manifest(),
        review_html_exists=review_html_exists,
        validation_markdown_exists=validation_markdown_exists,
    )


def _issue(
    code: IssueCode,
    severity: Severity,
    location: str = "paths./ping.get",
) -> Issue:
    return Issue(
        code=code,
        severity=severity,
        location=location,
        evidence=f"{code.value} evidence",
        suggested_fix=f"Fix {code.value}",
    )


def test_no_issues_produces_pass_with_full_scores() -> None:
    report = evaluate_score(_inputs(), profile=ScoreProfile.CI)

    assert report.status is ScoreStatus.PASS
    assert report.score == 100
    assert report.min_score == 85
    assert report.category_scores == {
        "openapi_validity": 100,
        "completeness": 100,
        "consistency": 100,
        "source_grounding": 100,
        "reviewability": 100,
    }
    assert report.findings == []


def test_ci_error_is_blocking_fail() -> None:
    report = evaluate_score(
        _inputs([_issue(IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR)]),
        profile=ScoreProfile.CI,
    )

    assert report.status is ScoreStatus.FAIL
    assert report.blocking_findings[0].code == "REQUIRED_INFO_MISSING"
    assert report.category_scores["completeness"] == 60
    assert report.score == 88


def test_review_profile_keeps_content_gap_as_needs_attention_when_score_passes() -> None:
    report = evaluate_score(
        _inputs([_issue(IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR)]),
        profile=ScoreProfile.REVIEW,
    )

    assert report.status is ScoreStatus.NEEDS_ATTENTION
    assert report.blocking_findings == []
    assert report.score == 88
    assert report.min_score == 70


def test_openapi_invalid_blocks_review_profile() -> None:
    report = evaluate_score(
        _inputs([_issue(IssueCode.OPENAPI_INVALID, Severity.ERROR, "openapi.yaml")]),
        profile=ScoreProfile.REVIEW,
    )

    assert report.status is ScoreStatus.FAIL
    assert report.category_scores["openapi_validity"] == 0
    assert report.blocking_findings[0].category is ScoreCategory.OPENAPI_VALIDITY


def test_warning_yields_needs_attention_and_nonblocking_penalty() -> None:
    report = evaluate_score(
        _inputs([_issue(IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING)]),
        profile=ScoreProfile.CI,
    )

    assert report.status is ScoreStatus.NEEDS_ATTENTION
    assert report.blocking_findings == []
    assert report.category_scores["completeness"] == 88
    assert report.score == 96


def test_min_score_override_can_fail_without_blocking_findings() -> None:
    report = evaluate_score(
        _inputs([_issue(IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING)]),
        profile=ScoreProfile.CI,
        min_score=97,
    )

    assert report.status is ScoreStatus.FAIL
    assert report.score == 96
    assert report.min_score == 97
    assert report.blocking_findings == []


def test_missing_review_artifacts_reduce_reviewability() -> None:
    report = evaluate_score(
        _inputs(review_html_exists=False, validation_markdown_exists=False),
        profile=ScoreProfile.CI,
    )

    assert report.status is ScoreStatus.NEEDS_ATTENTION
    assert report.category_scores["reviewability"] == 70
    assert [finding.code for finding in report.findings] == [
        "REVIEW_HTML_MISSING",
        "VALIDATION_MARKDOWN_MISSING",
    ]


def test_manifest_source_warnings_reduce_reviewability() -> None:
    report = evaluate_score(
        _inputs(manifest=_manifest(status=ProcessingStatus.UNSUPPORTED)),
        profile=ScoreProfile.CI,
    )

    assert report.status is ScoreStatus.NEEDS_ATTENTION
    assert report.category_scores["reviewability"] == 90
    assert report.findings[0].code == "SOURCE_UNSUPPORTED"
```

- [ ] **Step 2: Run evaluator tests to verify they fail**

Run:

```bash
uv run pytest tests/score/test_evaluate.py -v
```

Expected: FAIL during import with `ModuleNotFoundError: No module named 'loop_apidoc.score.evaluate'`.

- [ ] **Step 3: Add evaluator implementation**

Create `loop_apidoc/score/evaluate.py`:

```python
from __future__ import annotations

from loop_apidoc.manifest.models import ProcessingStatus
from loop_apidoc.score.models import (
    CATEGORY_WEIGHTS,
    ScoreCategory,
    ScoreFinding,
    ScoreInputs,
    ScoreProfile,
    ScoreReport,
    ScoreStatus,
    resolved_min_score,
)
from loop_apidoc.validate.models import Issue, IssueCode, Severity

_ISSUE_CATEGORY: dict[IssueCode, ScoreCategory] = {
    IssueCode.OPENAPI_INVALID: ScoreCategory.OPENAPI_VALIDITY,
    IssueCode.REQUIRED_INFO_MISSING: ScoreCategory.COMPLETENESS,
    IssueCode.OUTPUT_MISMATCH: ScoreCategory.CONSISTENCY,
    IssueCode.SOURCE_UNVERIFIED: ScoreCategory.SOURCE_GROUNDING,
    IssueCode.SOURCE_CONFLICT: ScoreCategory.SOURCE_GROUNDING,
    IssueCode.UNSUPPORTED_ASSERTION: ScoreCategory.SOURCE_GROUNDING,
}

_WARNING_PENALTY = 12
_ERROR_PENALTY = 40
_CODE_ERROR_PENALTY: dict[IssueCode, int] = {
    IssueCode.OPENAPI_INVALID: 100,
    IssueCode.UNSUPPORTED_ASSERTION: 50,
    IssueCode.SOURCE_CONFLICT: 50,
}

_REVIEW_BLOCKING_CODES = {
    IssueCode.OPENAPI_INVALID,
    IssueCode.OUTPUT_MISMATCH,
    IssueCode.SOURCE_CONFLICT,
    IssueCode.UNSUPPORTED_ASSERTION,
}


def _issue_penalty(issue: Issue) -> int:
    if issue.severity is Severity.WARNING:
        return _WARNING_PENALTY
    return _CODE_ERROR_PENALTY.get(issue.code, _ERROR_PENALTY)


def _is_blocking(issue: Issue, profile: ScoreProfile) -> bool:
    if issue.severity is not Severity.ERROR:
        return False
    if profile is ScoreProfile.CI:
        return True
    return issue.code in _REVIEW_BLOCKING_CODES


def _finding_from_issue(issue: Issue, profile: ScoreProfile) -> ScoreFinding:
    return ScoreFinding(
        code=issue.code.value,
        severity=issue.severity.value,
        location=issue.location,
        evidence=issue.evidence,
        suggested_fix=issue.suggested_fix,
        category=_ISSUE_CATEGORY[issue.code],
        blocking=_is_blocking(issue, profile),
        score_impact=_issue_penalty(issue),
    )


def _synthetic_finding(
    *,
    code: str,
    location: str,
    evidence: str,
    suggested_fix: str,
    score_impact: int,
) -> ScoreFinding:
    return ScoreFinding(
        code=code,
        severity=Severity.WARNING.value,
        location=location,
        evidence=evidence,
        suggested_fix=suggested_fix,
        category=ScoreCategory.REVIEWABILITY,
        blocking=False,
        score_impact=score_impact,
    )


def _reviewability_findings(inputs: ScoreInputs) -> list[ScoreFinding]:
    findings: list[ScoreFinding] = []
    if not inputs.review_html_exists:
        findings.append(
            _synthetic_finding(
                code="REVIEW_HTML_MISSING",
                location="review.html",
                evidence="run directory does not contain review.html",
                suggested_fix="Re-run assemble so the offline review page is generated.",
                score_impact=20,
            )
        )
    if not inputs.validation_markdown_exists:
        findings.append(
            _synthetic_finding(
                code="VALIDATION_MARKDOWN_MISSING",
                location="validation/report.md",
                evidence="run directory does not contain validation/report.md",
                suggested_fix="Re-run validation report writing for this run directory.",
                score_impact=10,
            )
        )
    for source in inputs.manifest.local_sources:
        if source.status is ProcessingStatus.UNSUPPORTED:
            findings.append(
                _synthetic_finding(
                    code="SOURCE_UNSUPPORTED",
                    location=f"manifest.json:{source.relative_path}",
                    evidence=f"{source.relative_path} is marked unsupported",
                    suggested_fix="Convert the unsupported input or remove it from the run.",
                    score_impact=10,
                )
            )
        elif source.status is ProcessingStatus.UNREADABLE:
            findings.append(
                _synthetic_finding(
                    code="SOURCE_UNREADABLE",
                    location=f"manifest.json:{source.relative_path}",
                    evidence=f"{source.relative_path} is marked unreadable",
                    suggested_fix="Fix permissions or replace the unreadable source.",
                    score_impact=15,
                )
            )
    return findings


def _category_scores(findings: list[ScoreFinding]) -> dict[str, int]:
    scores = {category.value: 100 for category in ScoreCategory}
    for finding in findings:
        key = finding.category.value
        scores[key] = max(0, scores[key] - finding.score_impact)
    return scores


def _weighted_total(category_scores: dict[str, int]) -> int:
    weighted = sum(
        category_scores[category] * weight
        for category, weight in CATEGORY_WEIGHTS.items()
    )
    return int(round(weighted / 100))


def _status(
    *,
    findings: list[ScoreFinding],
    category_scores: dict[str, int],
    score: int,
    min_score: int,
    profile: ScoreProfile,
) -> ScoreStatus:
    if any(finding.blocking for finding in findings):
        return ScoreStatus.FAIL
    if score < min_score:
        return ScoreStatus.FAIL
    category_gate = 70 if profile is ScoreProfile.CI else 60
    if any(value < category_gate for value in category_scores.values()):
        return ScoreStatus.NEEDS_ATTENTION
    if findings:
        return ScoreStatus.NEEDS_ATTENTION
    return ScoreStatus.PASS


def evaluate_score(
    inputs: ScoreInputs,
    *,
    profile: ScoreProfile = ScoreProfile.CI,
    min_score: int | None = None,
) -> ScoreReport:
    threshold = resolved_min_score(profile, min_score)
    findings = [
        _finding_from_issue(issue, profile)
        for issue in inputs.validation.issues
    ]
    findings.extend(_reviewability_findings(inputs))
    category_scores = _category_scores(findings)
    score = _weighted_total(category_scores)
    blocking_findings = [finding for finding in findings if finding.blocking]
    return ScoreReport(
        status=_status(
            findings=findings,
            category_scores=category_scores,
            score=score,
            min_score=threshold,
            profile=profile,
        ),
        score=score,
        profile=profile,
        min_score=threshold,
        category_scores=category_scores,
        blocking_findings=blocking_findings,
        findings=findings,
    )
```

Update `loop_apidoc/score/__init__.py`:

```python
"""Score reports for completed loop-apidoc run directories."""

from loop_apidoc.score.evaluate import evaluate_score
from loop_apidoc.score.loader import load_score_inputs
from loop_apidoc.score.models import (
    CATEGORY_WEIGHTS,
    DEFAULT_MIN_SCORES,
    ScoreCategory,
    ScoreFinding,
    ScoreInputError,
    ScoreInputs,
    ScoreProfile,
    ScoreReport,
    ScoreStatus,
    resolved_min_score,
)

__all__ = [
    "CATEGORY_WEIGHTS",
    "DEFAULT_MIN_SCORES",
    "ScoreCategory",
    "ScoreFinding",
    "ScoreInputError",
    "ScoreInputs",
    "ScoreProfile",
    "ScoreReport",
    "ScoreStatus",
    "evaluate_score",
    "load_score_inputs",
    "resolved_min_score",
]
```

- [ ] **Step 4: Run evaluator tests**

Run:

```bash
uv run pytest tests/score/test_evaluate.py -v
```

Expected: PASS.

- [ ] **Step 5: Run score package tests**

Run:

```bash
uv run pytest tests/score/test_models.py tests/score/test_loader.py tests/score/test_evaluate.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add loop_apidoc/score/__init__.py loop_apidoc/score/evaluate.py tests/score/test_evaluate.py
git commit -m "Evaluate API documentation score reports deterministically" -m "Map validation issues and review artifacts into profile-aware score reports.

Constraint: Evaluation is pure and cannot read files, spawn commands, fetch sources, or use LLM judgment.
Rejected: Make review profile ignore validation errors entirely | review intake still needs structural failures surfaced as blocking.
Confidence: high
Scope-risk: moderate
Directive: Tune penalties by editing the constants in evaluate.py with matching tests.
Tested: uv run pytest tests/score/test_models.py tests/score/test_loader.py tests/score/test_evaluate.py -v
Not-tested: Markdown rendering, CLI, and assemble integration are not implemented in this task."
```

## Task 4: Score Report Writers

**Files:**
- Modify: `loop_apidoc/score/__init__.py`
- Create: `loop_apidoc/score/report.py`
- Create: `tests/score/test_report.py`

- [ ] **Step 1: Write report rendering tests**

Create `tests/score/test_report.py`:

```python
from __future__ import annotations

from loop_apidoc.score.models import (
    ScoreCategory,
    ScoreFinding,
    ScoreProfile,
    ScoreReport,
    ScoreStatus,
)
from loop_apidoc.score.report import render_markdown, write_reports


def _report() -> ScoreReport:
    blocking = ScoreFinding(
        code="OPENAPI_INVALID",
        severity="error",
        location="openapi.yaml",
        evidence="openapi.yaml cannot be parsed",
        suggested_fix="Regenerate openapi.yaml.",
        category=ScoreCategory.OPENAPI_VALIDITY,
        blocking=True,
        score_impact=100,
    )
    warning = ScoreFinding(
        code="REVIEW_HTML_MISSING",
        severity="warning",
        location="review.html",
        evidence="review page is absent",
        suggested_fix="Re-run assemble.",
        category=ScoreCategory.REVIEWABILITY,
        blocking=False,
        score_impact=20,
    )
    return ScoreReport(
        status=ScoreStatus.FAIL,
        score=78,
        profile=ScoreProfile.CI,
        min_score=85,
        category_scores={
            "openapi_validity": 0,
            "completeness": 100,
            "consistency": 100,
            "source_grounding": 100,
            "reviewability": 80,
        },
        blocking_findings=[blocking],
        findings=[blocking, warning],
    )


def test_render_markdown_includes_summary_categories_and_findings() -> None:
    md = render_markdown(_report())

    assert "# API Documentation Score Report" in md
    assert "Status: **FAIL**" in md
    assert "Score: **78 / 100**" in md
    assert "| openapi_validity | 0 |" in md
    assert "## Blocking Findings" in md
    assert "**OPENAPI_INVALID**" in md
    assert "## Recommended Fixes" in md
    assert "../validation/report.md" in md
    assert "../review.html" in md


def test_write_reports_emits_score_json_and_markdown(tmp_path) -> None:
    out = tmp_path / "score"
    write_reports(_report(), out)

    loaded = ScoreReport.model_validate_json((out / "score.json").read_text())

    assert loaded == _report()
    assert "API Documentation Score Report" in (out / "score.md").read_text(
        encoding="utf-8"
    )
```

- [ ] **Step 2: Run report tests to verify they fail**

Run:

```bash
uv run pytest tests/score/test_report.py -v
```

Expected: FAIL during import with `ModuleNotFoundError: No module named 'loop_apidoc.score.report'`.

- [ ] **Step 3: Add report writer implementation**

Create `loop_apidoc/score/report.py`:

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.score.models import ScoreFinding, ScoreReport


def _finding_bullet(finding: ScoreFinding) -> str:
    return (
        f"- **{finding.code}** ({finding.severity}) @ `{finding.location}`\n"
        f"  - Category: `{finding.category.value}`\n"
        f"  - Score impact: {finding.score_impact}\n"
        f"  - Evidence: {finding.evidence}\n"
        f"  - Suggested fix: {finding.suggested_fix}"
    )


def render_markdown(report: ScoreReport) -> str:
    status = report.status.value.upper()
    lines = [
        "# API Documentation Score Report",
        "",
        f"Status: **{status}**",
        f"Score: **{report.score} / 100**",
        f"Profile: `{report.profile.value}`",
        f"Minimum score: `{report.min_score}`",
        "",
        "## Category Scores",
        "",
        "| Category | Score |",
        "| --- | ---: |",
    ]
    for category, score in report.category_scores.items():
        lines.append(f"| {category} | {score} |")

    lines.extend(
        [
            "",
            "## Artifact Links",
            "",
            "- Validation report: `../validation/report.md`",
            "- Offline review page: `../review.html`",
            "- OpenAPI contract: `../openapi.yaml`",
            "- Provenance: `../provenance.json`",
            "",
            "## Blocking Findings",
            "",
        ]
    )
    if report.blocking_findings:
        lines.extend(_finding_bullet(finding) for finding in report.blocking_findings)
    else:
        lines.append("_No blocking findings._")

    non_blocking = [finding for finding in report.findings if not finding.blocking]
    lines.extend(["", "## Non-Blocking Findings", ""])
    if non_blocking:
        lines.extend(_finding_bullet(finding) for finding in non_blocking)
    else:
        lines.append("_No non-blocking findings._")

    lines.extend(["", "## Recommended Fixes", ""])
    if report.findings:
        for finding in sorted(report.findings, key=lambda item: item.score_impact, reverse=True):
            lines.append(f"- `{finding.location}`: {finding.suggested_fix}")
    else:
        lines.append("_No fixes recommended._")

    return "\n".join(lines).rstrip() + "\n"


def write_reports(report: ScoreReport, score_dir: Path) -> None:
    score_dir.mkdir(parents=True, exist_ok=True)
    (score_dir / "score.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (score_dir / "score.md").write_text(render_markdown(report), encoding="utf-8")
```

Update `loop_apidoc/score/__init__.py`:

```python
"""Score reports for completed loop-apidoc run directories."""

from loop_apidoc.score.evaluate import evaluate_score
from loop_apidoc.score.loader import load_score_inputs
from loop_apidoc.score.models import (
    CATEGORY_WEIGHTS,
    DEFAULT_MIN_SCORES,
    ScoreCategory,
    ScoreFinding,
    ScoreInputError,
    ScoreInputs,
    ScoreProfile,
    ScoreReport,
    ScoreStatus,
    resolved_min_score,
)
from loop_apidoc.score.report import render_markdown, write_reports

__all__ = [
    "CATEGORY_WEIGHTS",
    "DEFAULT_MIN_SCORES",
    "ScoreCategory",
    "ScoreFinding",
    "ScoreInputError",
    "ScoreInputs",
    "ScoreProfile",
    "ScoreReport",
    "ScoreStatus",
    "evaluate_score",
    "load_score_inputs",
    "render_markdown",
    "resolved_min_score",
    "write_reports",
]
```

- [ ] **Step 4: Run report tests**

Run:

```bash
uv run pytest tests/score/test_report.py -v
```

Expected: PASS.

- [ ] **Step 5: Run score package tests**

Run:

```bash
uv run pytest tests/score -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add loop_apidoc/score/__init__.py loop_apidoc/score/report.py tests/score/test_report.py
git commit -m "Write score reports as JSON and Markdown artifacts" -m "Add human and machine-readable report output for evaluated score reports.

Constraint: Report writing is the only file-output layer inside the score package.
Confidence: high
Scope-risk: narrow
Directive: Keep score.md concise and linked to authoritative run artifacts instead of repeating API schemas.
Tested: uv run pytest tests/score -v
Not-tested: CLI and assemble integration are not implemented in this task."
```

## Task 5: Score CLI Command

**Files:**
- Modify: `loop_apidoc/cli.py`
- Create: `tests/test_cli_score.py`

- [ ] **Step 1: Write CLI tests**

Create `tests/test_cli_score.py`:

```python
from __future__ import annotations

import json

from typer.testing import CliRunner

from loop_apidoc.cli import app
from tests.score.test_loader import write_score_run

runner = CliRunner()


def test_score_command_writes_reports_and_prints_json(tmp_path) -> None:
    run_dir = write_score_run(tmp_path / "run")

    result = runner.invoke(app, ["score", "--output", str(run_dir), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["score"] == 100
    assert (run_dir / "score" / "score.json").is_file()
    assert (run_dir / "score" / "score.md").is_file()


def test_score_command_plain_output_mentions_status_and_report(tmp_path) -> None:
    run_dir = write_score_run(tmp_path / "run")

    result = runner.invoke(app, ["score", "--output", str(run_dir)])

    assert result.exit_code == 0
    assert "score PASS" in result.stdout
    assert "score/score.json" in result.stdout


def test_score_command_needs_attention_exits_1(tmp_path) -> None:
    run_dir = write_score_run(tmp_path / "run")
    (run_dir / "review.html").unlink()

    result = runner.invoke(app, ["score", "--output", str(run_dir), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "needs_attention"


def test_score_command_review_profile_uses_review_threshold(tmp_path) -> None:
    run_dir = write_score_run(tmp_path / "run")

    result = runner.invoke(
        app,
        ["score", "--output", str(run_dir), "--profile", "review", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["profile"] == "review"
    assert payload["min_score"] == 70


def test_score_command_input_error_exits_2_without_output_dir(tmp_path) -> None:
    run_dir = write_score_run(tmp_path / "run")
    (run_dir / "manifest.json").unlink()

    result = runner.invoke(app, ["score", "--output", str(run_dir)])

    assert result.exit_code == 2
    assert "score input error" in result.stderr
    assert not (run_dir / "score").exists()
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run:

```bash
uv run pytest tests/test_cli_score.py -v
```

Expected: FAIL with Typer reporting no `score` command.

- [ ] **Step 3: Add score command to CLI**

Modify the top of `loop_apidoc/cli.py` so the imports include `Annotated` and `ScoreProfile`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.run.runid import make_run_id
from loop_apidoc.score.models import ScoreProfile
from loop_apidoc.validate import validate_run_dir, write_reports
```

Insert this command between `diff` and `assemble`:

```python
@app.command()
def score(
    output: Path = typer.Option(
        ...,
        "--output",
        help="已完成的 run 目錄（含 openapi.yaml / provenance.json / validation/report.json）",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    profile: ScoreProfile = typer.Option(
        ScoreProfile.CI,
        "--profile",
        case_sensitive=False,
        help="評分嚴格度：ci 較嚴格，review 較適合人工健檢",
    ),
    min_score: Annotated[
        int | None,
        typer.Option("--min-score", min=0, max=100, help="覆寫 profile 預設分數門檻"),
    ] = None,
    json_out: bool = typer.Option(
        False,
        "--json",
        help="把 score report JSON 印到 stdout",
    ),
) -> None:
    """評分既有 run 目錄並寫出 score/score.{json,md}。"""
    from loop_apidoc.score import (
        ScoreInputError,
        evaluate_score,
        load_score_inputs,
        write_reports as write_score_reports,
    )

    score_dir = output / "score"
    try:
        inputs = load_score_inputs(output)
        report = evaluate_score(inputs, profile=profile, min_score=min_score)
    except ScoreInputError as exc:
        typer.echo(f"score input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    write_score_reports(report, score_dir)
    if json_out:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(
            f"score {report.status.value.upper()}: {report.score}/100 "
            f"(profile {report.profile.value}, min {report.min_score})；"
            f"報告寫入 {score_dir / 'score.json'}"
        )
    raise typer.Exit(code=0 if report.status.value == "pass" else 1)
```

- [ ] **Step 4: Run CLI score tests**

Run:

```bash
uv run pytest tests/test_cli_score.py -v
```

Expected: PASS.

- [ ] **Step 5: Run score package and CLI tests**

Run:

```bash
uv run pytest tests/score tests/test_cli_score.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

Run:

```bash
git add loop_apidoc/cli.py tests/test_cli_score.py
git commit -m "Expose score reports through the CLI" -m "Add loop-apidoc score for completed run directories.

Constraint: CLI input errors use exit code 2 and successful scoring writes both JSON and Markdown reports.
Confidence: high
Scope-risk: moderate
Directive: Preserve score JSON stdout for CI and agent callers.
Tested: uv run pytest tests/score tests/test_cli_score.py -v
Not-tested: assemble --score wiring is not implemented in this task."
```

## Task 6: Assemble Score Wiring

**Files:**
- Modify: `loop_apidoc/cli.py`
- Modify: `tests/test_cli_assemble.py`

- [ ] **Step 1: Add assemble scoring tests**

Append these tests to `tests/test_cli_assemble.py`:

```python

def test_assemble_score_writes_score_reports_and_preserves_exit_status(tmp_path):
    sources, extraction, out = _setup(tmp_path)

    res = runner.invoke(app, [
        "assemble",
        "--sources", str(sources),
        "--extraction", str(extraction),
        "--output", str(out),
        "--score",
        "--json",
    ])

    assert res.exit_code in (0, 1)
    payload = json.loads(res.stdout)
    run_dir = Path(payload["run_dir"])
    assert "score" in payload
    assert payload["score"]["status"] in {"pass", "needs_attention", "fail"}
    assert (run_dir / "score" / "score.json").is_file()
    assert (run_dir / "score" / "score.md").is_file()
    assert res.exit_code == (0 if payload["ok"] else 1)


def test_assemble_without_score_does_not_write_score_reports(tmp_path):
    sources, extraction, out = _setup(tmp_path)

    res = runner.invoke(app, [
        "assemble",
        "--sources", str(sources),
        "--extraction", str(extraction),
        "--output", str(out),
        "--json",
    ])

    payload = json.loads(res.stdout)
    assert "score" not in payload
    assert not (Path(payload["run_dir"]) / "score").exists()
```

- [ ] **Step 2: Run assemble tests to verify they fail**

Run:

```bash
uv run pytest tests/test_cli_assemble.py -k "score" -v
```

Expected: FAIL because `assemble` does not accept `--score`.

- [ ] **Step 3: Add `--score` option and report writing**

Modify the `assemble` function signature in `loop_apidoc/cli.py` by adding this option after `json_out`:

```python
    score_report: bool = typer.Option(
        False,
        "--score",
        help="在 assemble 完成後寫出 score/score.{json,md}",
    ),
```

Inside `assemble`, after `run_assemble_pipeline(...)` succeeds and before `if json_out:`, add:

```python
    score_payload = None
    score_error = None
    if score_report:
        from loop_apidoc.score import (
            ScoreInputError,
            evaluate_score,
            load_score_inputs,
            write_reports as write_score_reports,
        )

        try:
            score_inputs = load_score_inputs(Path(result.run_dir))
            score_payload = evaluate_score(score_inputs)
            write_score_reports(score_payload, Path(result.run_dir) / "score")
        except ScoreInputError as exc:
            score_error = str(exc)
            typer.echo(f"score input error: {exc}", err=True)
```

In the `json_out` payload block, add score fields before `typer.echo(...)`:

```python
        if score_payload is not None:
            payload["score"] = score_payload.model_dump(mode="json")
        if score_error is not None:
            payload["score_error"] = score_error
```

In the non-JSON output branch, replace the current `typer.echo(...)` call with:

```python
        suffix = ""
        if score_payload is not None:
            suffix = (
                f"；score {score_payload.status.value.upper()} "
                f"{score_payload.score}/100"
            )
        elif score_error is not None:
            suffix = f"；score input error: {score_error}"
        typer.echo(
            f"狀態 {result.status.value}:error {len(result.report.errors())}，"
            f"warning {len(result.report.warnings())}；輸出於 {result.run_dir}；"
            f"核對頁 {Path(result.run_dir) / 'review.html'}"
            f"{suffix}"
        )
```

Keep the existing final exit line:

```python
    raise typer.Exit(code=0 if result.ok else 1)
```

- [ ] **Step 4: Run focused assemble score tests**

Run:

```bash
uv run pytest tests/test_cli_assemble.py -k "score" -v
```

Expected: PASS.

- [ ] **Step 5: Run CLI score and assemble tests**

Run:

```bash
uv run pytest tests/test_cli_score.py tests/test_cli_assemble.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

Run:

```bash
git add loop_apidoc/cli.py tests/test_cli_assemble.py
git commit -m "Let assemble write score reports on request" -m "Wire optional score report generation after assemble produces a run directory.

Constraint: assemble exit codes remain driven by the existing validation result.
Rejected: Make assemble fail when score status is fail | scoring is a report layer here, not a replacement for assemble validation semantics.
Confidence: high
Scope-risk: moderate
Directive: Keep score errors visible in JSON and stderr without masking assemble status.
Tested: uv run pytest tests/test_cli_score.py tests/test_cli_assemble.py -v
Not-tested: Full repository regression is left for the final verification task."
```

## Task 7: README and Architecture Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Patch README usage and output docs**

In `README.md`, add this section after the `validate` command section and before `diff`:

````markdown
### `score` — 評分既有 run 目錄

```bash
uv run loop-apidoc score --output ./output/<run-id> [--profile ci|review] [--min-score 85] [--json]
```

讀取既有 run 目錄的 `validation/report.json`、`openapi.yaml`、
`provenance.json`、`manifest.json` 與選填的 `plan/normalization-plan.json`，
輸出 `score/score.json` 與 `score/score.md`。`ci` profile 預設門檻為
`85`，`review` profile 預設門檻為 `70`。退出碼：`0` = pass，`1` =
needs_attention / fail，`2` = run-dir 輸入錯誤。
````

In the `assemble` command example in `README.md`, change:

```markdown
  [--url <URL> ...] [--json]
```

to:

```markdown
  [--url <URL> ...] [--json] [--score]
```

In the assemble description paragraph, append:

```markdown
加上 `--score` 時，`assemble` 完成後會額外寫出 `score/score.json` 與
`score/score.md`；assemble 的退出碼仍維持既有驗證語意。
```

In the output tree, insert after `validation/`:

```text
    ├── score/                       # 文件品質評分（使用 loop-apidoc score 或 assemble --score）
    │   ├── score.json
    │   └── score.md
```

In the package structure table, add:

```markdown
| `loop_apidoc/score/` | 既有 run-dir 文件品質評分(JSON/Markdown report, CI gate 狀態) |
```

- [ ] **Step 2: Patch architecture docs**

In `docs/ARCHITECTURE.md`, update the CLI command list sentence from:

```markdown
`cli.py`(Typer)暴露五個指令:`preprocess`(PDF→markdown)、`manifest`(掃描)、`assemble`(組裝 + 驗證)、`validate`(驗證既有 run-dir)、`diff`(比較兩個已完成 run-dir 的版本差異)。
```

to:

```markdown
`cli.py`(Typer)暴露六個指令:`preprocess`(PDF→markdown)、`manifest`(掃描)、`assemble`(組裝 + 驗證,可選 `--score`)、`validate`(驗證既有 run-dir)、`score`(評分既有 run-dir)、`diff`(比較兩個已完成 run-dir 的版本差異)。
```

In the package boundary mermaid graph, add `score` as a CLI target:

```mermaid
    cli --> score[score/<br/>run-dir 評分 + 報告]
```

In the data-flow table, add:

```markdown
| 評分(可選) | `load_score_inputs(run_dir)` → `evaluate_score(inputs, profile, min_score)` → `write_reports(report, score_dir)` | `<run-dir>/score/score.{json,md}` |
```

In the assemble flow paragraph, add:

```markdown
`assemble --score` 在驗證報告寫出後讀取同一個 run-dir artifact 集合並產生
`score/score.{json,md}`；這是後段品質摘要，不會回頭擷取來源，也不改變
validation pass/fail 的語意。
```

- [ ] **Step 3: Run documentation diff check**

Run:

```bash
git diff --check README.md docs/ARCHITECTURE.md
```

Expected: no output.

- [ ] **Step 4: Commit Task 7**

Run:

```bash
git add README.md docs/ARCHITECTURE.md
git commit -m "Document score reports as a first-class run artifact" -m "Explain the score command, assemble score option, output tree, and architecture boundary.

Constraint: Documentation must preserve validation as the authoritative pass/fail source for assemble.
Confidence: high
Scope-risk: narrow
Directive: Keep score docs framed as quality summary, not as a source-recovery mechanism.
Tested: git diff --check README.md docs/ARCHITECTURE.md
Not-tested: Documentation-only task; code tests are covered by prior tasks."
```

## Task 8: Final Verification

**Files:**
- No source changes expected unless verification exposes a defect.

- [ ] **Step 1: Run full score and CLI test set**

Run:

```bash
uv run pytest tests/score tests/test_cli_score.py tests/test_cli_assemble.py tests/test_cli_diff.py -v
```

Expected: PASS.

- [ ] **Step 2: Run repository tests**

Run:

```bash
uv run pytest
```

Expected: PASS. If benchmark tests skip because operator-provided sources are absent, record the skip count in the final implementation report.

- [ ] **Step 3: Run lint**

Run:

```bash
uv run ruff check .
```

Expected: PASS.

- [ ] **Step 4: Run quality gate when benchmark sources are present**

Run:

```bash
uv run python scripts/quality_gate.py
```

Expected: PASS when all benchmark source directories required by the gate are present. If it reports missing benchmark sources, record that exact missing-source list and do not claim quality-gate pass.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git status --short
git diff --stat
git diff --check
```

Expected:

- `git status --short` lists only intended score, CLI, docs, and test files.
- `git diff --check` produces no output.

- [ ] **Step 6: Commit final verification fixes or record clean state**

If Step 1 through Step 5 required code fixes, commit them:

```bash
git add loop_apidoc tests README.md docs/ARCHITECTURE.md
git commit -m "Verify score reports across CLI and regression tests" -m "Address final integration issues found during verification.

Constraint: Final fixes are limited to score reports and their command wiring.
Confidence: high
Scope-risk: narrow
Directive: Do not broaden score into source extraction or code-to-document behavior in this verification pass.
Tested: uv run pytest tests/score tests/test_cli_score.py tests/test_cli_assemble.py tests/test_cli_diff.py -v; uv run pytest; uv run ruff check .; git diff --check
Not-tested: scripts/quality_gate.py if benchmark sources are unavailable."
```

If no fixes are required after Task 7, do not create an empty commit. Record the clean verification evidence in the final response.

## Self-Review

**Spec coverage:** The plan covers first-class `score` CLI, JSON and Markdown reports, `status + score + category_scores + blocking_findings`, `ci` and `review` profiles, `--min-score`, deterministic run-dir artifact loading, exit codes `0/1/2`, optional `assemble --score`, no LLM judgment, and code-to-document reuse only through the completed run-dir artifact contract.

**Scope check:** The plan intentionally excludes route/controller/schema extraction. It adds one bounded score package and one CLI option.

**Type consistency:** The plan uses `ScoreProfile`, `ScoreStatus`, `ScoreCategory`, `ScoreFinding`, `ScoreReport`, `ScoreInputs`, `ScoreInputError`, `load_score_inputs`, `evaluate_score`, and `write_reports` consistently across tasks. Category score keys are serialized strings, while finding categories remain enums that Pydantic serializes as strings.

**Validation path:** The smallest proof starts with `tests/score/test_models.py`, expands through loader/evaluator/report tests, adds CLI tests, then verifies assemble wiring and docs.
