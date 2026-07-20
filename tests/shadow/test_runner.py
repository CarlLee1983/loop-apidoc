from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.core.models import LifecycleState
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import (
    ContractTestCase,
    CryptoScheme,
    EndpointEntry,
    FieldCondition,
    IntegrationContract,
    NormalizationPlan,
    PlanItemStatus,
    SchemaEntry,
    SourceCitation,
    SystemGroup,
)
from loop_apidoc.run.models import RunStatus
from loop_apidoc.shadow.runner import execute_shadow
from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)


NOW = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)


def _manifest() -> Manifest:
    return Manifest(
        sources_root="/sources",
        generated_at=NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=10,
                sha256="a" * 64,
                scanned_at=NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )


def _plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="",
        system_groups=[SystemGroup(name="Demo API", version="1")],
        endpoints=[
            EndpointEntry(
                status=PlanItemStatus.SUPPORTED,
                citations=[
                    SourceCitation(
                        query_id="06-ep0",
                        answer_path="answer.json",
                        manifest_source="manual.md",
                    )
                ],
                method="GET",
                path="/ping",
                responses=[{"status": "200", "description": "OK"}],
            )
        ],
    )


def test_runner_executes_through_core_validation_without_approval_or_publication():
    artifacts = execute_shadow(
        manifest=_manifest(),
        plan=_plan(),
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    assert artifacts.workflow.state is LifecycleState.APPROVAL_READY
    assert artifacts.artifact_publications == 0
    assert artifacts.approval_requests == 0
    assert artifacts.events[-1].kind == "lifecycle.approval_ready"
    assert artifacts.contract.operations[0].path == "/ping"
    assert artifacts.decision.verdict.value == "accept"
    assert artifacts.comparison.verdict_match is True


def test_runner_executes_when_legacy_validation_failed():
    legacy_report = ValidationReport(
        issues=[
            Issue(
                code=IssueCode.REQUIRED_INFO_MISSING,
                severity=Severity.ERROR,
                location="paths./ping.get",
                evidence="source",
                suggested_fix="fill",
            )
        ]
    )

    artifacts = execute_shadow(
        manifest=_manifest(),
        plan=_plan(),
        legacy_report=legacy_report,
        legacy_status=RunStatus.FAILED,
        generated_at=NOW,
    )

    assert artifacts.workflow.state is LifecycleState.APPROVAL_READY
    assert artifacts.comparison.legacy_status == "failed"
    assert artifacts.comparison.verdict_match is False


def test_runner_preserves_unknown_nested_and_integration_values():
    citation = _plan().endpoints[0].citations
    plan = _plan().model_copy(
        update={
            "endpoints": [
                EndpointEntry(
                    status=PlanItemStatus.SUPPORTED,
                    citations=citation,
                    method="GET",
                    path="/search",
                    parameters=[{"name": "q", "in": "query"}],
                    responses=[{"status": "200"}],
                )
            ],
            "schemas": [
                SchemaEntry(
                    status=PlanItemStatus.SUPPORTED,
                    citations=citation,
                    name="Result",
                    fields=[{"name": "value", "type": "string"}],
                )
            ],
            "integration": IntegrationContract(
                crypto=[
                    CryptoScheme(
                        status=PlanItemStatus.SUPPORTED,
                        citations=citation,
                        name="OpaqueMechanic",
                    )
                ],
                field_conditions=[
                    FieldCondition(
                        status=PlanItemStatus.SUPPORTED,
                        citations=citation,
                        scope="Result.value",
                    )
                ],
                test_cases=[
                    ContractTestCase(
                        status=PlanItemStatus.SUPPORTED,
                        citations=citation,
                        name="source example",
                    )
                ],
            ),
        }
    )

    artifacts = execute_shadow(
        manifest=_manifest(),
        plan=plan,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    assert artifacts.contract.operations[0].parameters[0].required is None
    assert artifacts.contract.schemas[0].fields[0].required is None
    assert all(
        mechanic.kind is None
        for mechanic in artifacts.contract.integration_mechanics
    )


def test_runner_preserves_structured_citation_diagnostic_lineage():
    plan = _plan().model_copy(
        update={
            "endpoints": [
                EndpointEntry(
                    status=PlanItemStatus.SUPPORTED,
                    citations=[
                        SourceCitation(
                            query_id="06-ep9",
                            answer_path="answers/06-ep9.json",
                            manifest_source="missing.md",
                            locator="p.9",
                        )
                    ],
                    method="GET",
                    path="/unresolved",
                    responses=[{"status": "200"}],
                )
            ]
        }
    )

    artifacts = execute_shadow(
        manifest=_manifest(),
        plan=plan,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    diagnostic = artifacts.comparison.diagnostics[0]
    assert diagnostic.code == "CITATION_UNRESOLVED"
    assert diagnostic.plan_location == "endpoints[0]"
    assert diagnostic.manifest_source == "missing.md"
    assert diagnostic.query_id == "06-ep9"
    assert diagnostic.answer_path == "answers/06-ep9.json"


def test_runner_keeps_single_value_conflict_as_unverified_claim():
    plan = _plan().model_copy(
        update={
            "endpoints": [
                EndpointEntry(
                    status=PlanItemStatus.CONFLICTING,
                    citations=_plan().endpoints[0].citations,
                    method="GET",
                    path="/conflict",
                    responses=[{"status": "200"}],
                )
            ]
        }
    )

    artifacts = execute_shadow(
        manifest=_manifest(),
        plan=plan,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    assert len(artifacts.claims) == 1
    assert artifacts.claims[0].status.value == "unverified"
