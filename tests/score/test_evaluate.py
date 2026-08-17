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


def _manifest(
    *,
    status: ProcessingStatus = ProcessingStatus.PENDING,
    source_format: SourceFormat = SourceFormat.MARKDOWN,
) -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=source_format,
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
    openapi: dict | None = None,
    plan: dict | None = None,
    review_html_exists: bool = True,
    validation_markdown_exists: bool = True,
    manifest: Manifest | None = None,
) -> ScoreInputs:
    return ScoreInputs(
        run_dir=run_dir,
        openapi=openapi
        or {"openapi": "3.1.0", "info": {"title": "Demo"}, "paths": {}},
        validation=ValidationReport(issues=issues or []),
        provenance=ProvenanceDocument(notebook_url="", entries=[]),
        manifest=manifest or _manifest(),
        plan=plan,
        review_html_exists=review_html_exists,
        validation_markdown_exists=validation_markdown_exists,
    )


def _issue(
    code: IssueCode,
    severity: Severity,
    location: str = "paths./ping.get",
    field_path: str | None = None,
) -> Issue:
    return Issue(
        code=code,
        severity=severity,
        location=location,
        evidence=f"{code.value} evidence",
        suggested_fix=f"Fix {code.value}",
        field_path=field_path,
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


def test_score_report_carries_response_contract_metrics() -> None:
    openapi = {
        "openapi": "3.1.0",
        "info": {"title": "Demo"},
        "paths": {
            "/usable": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "name": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        }
                    }
                }
            },
            "/hollow": {"get": {"responses": {"200": {"description": "OK"}}}},
        },
    }

    report = evaluate_score(_inputs(openapi=openapi), profile=ScoreProfile.CI)

    assert report.response_contract.path_operations == 2
    assert report.response_contract.operations_with_usable_schema == 1
    assert report.response_contract.hollow_operations == 1
    assert report.response_contract.field_count == 2


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


def test_declared_missing_examples_remain_visible_without_penalty() -> None:
    issue = _issue(
        IssueCode.REQUIRED_INFO_MISSING,
        Severity.WARNING,
        "paths./ping.get",
        field_path="examples",
    )

    report = evaluate_score(
        _inputs(
            [issue],
            plan={
                "missing_items": [
                    {
                        "area": "06",
                        "detail": "examples",
                        "query_id": "06-ep0",
                        "operation_location": "paths./ping.get",
                    }
                ]
            },
        ),
        profile=ScoreProfile.CI,
    )

    assert report.findings[0].score_impact == 0
    assert report.category_scores["completeness"] == 100


def test_unclassified_missing_examples_keep_penalty() -> None:
    issue = _issue(
        IssueCode.REQUIRED_INFO_MISSING,
        Severity.WARNING,
        "paths./ping.get",
        field_path="examples",
    )

    report = evaluate_score(_inputs([issue]), profile=ScoreProfile.CI)

    assert report.findings[0].score_impact == 12


def test_declared_non_example_gap_keeps_penalty() -> None:
    issue = _issue(
        IssueCode.REQUIRED_INFO_MISSING,
        Severity.WARNING,
        "paths./ping.get",
        field_path="examples",
    )

    report = evaluate_score(
        _inputs(
            [issue],
            plan={
                "missing_items": [
                    {
                        "area": "06",
                        "detail": "response fields",
                        "query_id": "06-ep0",
                        "operation_location": "paths./ping.get",
                    }
                ]
            },
        ),
        profile=ScoreProfile.CI,
    )

    assert report.findings[0].score_impact == 12


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


def test_the_unsupported_finding_names_the_format_s_own_next_step() -> None:
    """「轉成受支援的格式」對拿著 .xlsx 的人等於沒說。分數不變,可行動性才變。"""
    report = evaluate_score(
        _inputs(
            manifest=_manifest(
                status=ProcessingStatus.UNSUPPORTED,
                source_format=SourceFormat.SPREADSHEET,
            )
        ),
        profile=ScoreProfile.CI,
    )

    unsupported = next(
        f for f in report.findings if f.code == "SOURCE_UNSUPPORTED"
    )
    assert "Markdown table" in unsupported.suggested_fix


def test_issue_category_mapping_covers_every_scored_issue_code() -> None:
    # 每個「會計分」的 code 都必須有類別;刻意不計分的則必須明列在
    # _UNSCORED_CODES,好讓新增 code 的人被迫二選一,而不是漏掉。
    from loop_apidoc.score.evaluate import _ISSUE_CATEGORY, _UNSCORED_CODES

    assert set(_ISSUE_CATEGORY) | _UNSCORED_CODES == set(IssueCode)
    assert not set(_ISSUE_CATEGORY) & _UNSCORED_CODES


def test_an_unscanned_source_scores_against_source_grounding() -> None:
    # 「無法對這份來源執行語意完整性檢查」講的是來源可信度,不是成品缺了資訊,
    # 所以扣在 source_grounding;兩次 run 的分差因此能表達「這次有更多來源沒被檢查」。
    report = evaluate_score(
        _inputs([_issue(IssueCode.SOURCE_FACTS_UNSCANNED, Severity.WARNING,
                        location="dump.md")]),
        profile=ScoreProfile.CI,
    )

    assert report.category_scores[ScoreCategory.SOURCE_GROUNDING.value] < 100
    assert report.findings[0].category is ScoreCategory.SOURCE_GROUNDING


def test_focus_outcomes_never_reach_the_score() -> None:
    # ADR 0004:分數只看來源說了什麼,不看誰問了什麼。計入 FOCUS_UNMET 會讓同一
    # 份來源因 focus 不同而得到不同分數,提出者也能靠寫寬鬆的 directive 拉高分數。
    from loop_apidoc.score.evaluate import _UNSCORED_CODES

    assert IssueCode.FOCUS_UNMET in _UNSCORED_CODES
    # 記載錯誤碼下界的短少同理:它是「提出者要求收齊」的結局,不是來源品質。
    assert IssueCode.FOCUS_INCOMPLETE in _UNSCORED_CODES
