from __future__ import annotations

import json
from datetime import datetime, timezone

from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import (
    ContractMissing,
    IntegrationContract,
    MissingItem,
    NormalizationPlan,
    SourceConflict,
    UnverifiedItem,
)
from loop_apidoc.preparation import (
    PreparationStatus,
    assess_preparation,
    render_markdown,
)

_NOW = datetime(2026, 6, 30, 8, 0, tzinfo=timezone.utc)


def _manifest(*, supported: bool = True) -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=12,
                sha256="abc",
                scanned_at=_NOW,
                supported=supported,
                status=ProcessingStatus.PENDING
                if supported
                else ProcessingStatus.UNSUPPORTED,
            )
        ],
    )


def _inventory() -> dict:
    return {
        "title": "Demo API",
        "overview": "Demo",
        "endpoints": [{"method": "GET", "path": "/ping"}],
        "missing": [],
    }


def _endpoint() -> str:
    return json.dumps(
        {
            "method": "GET",
            "path": "/ping",
            "responses": [{"status": "200", "description": "OK"}],
            "missing": [],
        },
        ensure_ascii=False,
    )


def test_ready_report_scores_all_pre_generation_phases():
    report = assess_preparation(
        manifest=_manifest(),
        inventory=_inventory(),
        endpoint_texts=[_endpoint()],
        plan=NormalizationPlan(
            notebook_url="",
            integration=IntegrationContract(),
        ),
    )

    assert report.status is PreparationStatus.READY
    assert report.summary == {"blocked": 0, "needs_attention": 0, "ready": 4}
    assert [phase.id for phase in report.phases] == [
        "sources",
        "extraction",
        "normalization_plan",
        "integration_contract",
    ]
    assert all(not phase.findings for phase in report.phases)


def test_attention_report_surfaces_structured_self_correction_targets():
    inventory = {**_inventory(), "missing": [{"area": "auth", "detail": "api key"}]}
    endpoint = json.dumps(
        {
            "method": "POST",
            "path": "/pay",
            "responses": [],
            "missing": ["response example"],
        },
        ensure_ascii=False,
    )
    plan = NormalizationPlan(
        notebook_url="",
        missing_items=[MissingItem(area="auth", detail="api key", query_id="05")],
        source_conflicts=[
            SourceConflict(area="fees", detail="two fee tables disagree", query_id="07")
        ],
        unverified_items=[
            UnverifiedItem(area="retry", detail="timeout missing", query_id="10")
        ],
        integration=IntegrationContract(
            missing=[ContractMissing(area="crypto", detail="AES mode not stated")]
        ),
    )

    report = assess_preparation(
        manifest=_manifest(),
        inventory=inventory,
        endpoint_texts=[endpoint],
        plan=plan,
    )

    assert report.status is PreparationStatus.BLOCKED
    findings = [finding for phase in report.phases for finding in phase.findings]
    assert any(
        finding.target_file == "inventory.json"
        and finding.field_path == "/missing/0"
        and "re-read source" in finding.suggested_action
        for finding in findings
    )
    assert any(
        finding.target_file == "endpoints/ep0.json"
        and finding.field_path == "/missing/0"
        for finding in findings
    )
    assert any(finding.severity == "error" and "conflict" in finding.summary for finding in findings)
    assert report.summary["blocked"] == 1
    assert report.summary["needs_attention"] == 2


def test_blocked_when_no_supported_sources_or_endpoint_details():
    report = assess_preparation(
        manifest=_manifest(supported=False),
        inventory={**_inventory(), "endpoints": []},
        endpoint_texts=[],
        plan=NormalizationPlan(notebook_url=""),
    )

    assert report.status is PreparationStatus.BLOCKED
    findings = [finding for phase in report.phases for finding in phase.findings]
    assert any("supported source" in finding.summary for finding in findings)
    assert any("endpoint detail" in finding.summary for finding in findings)


def test_render_markdown_includes_phase_status_and_actions():
    report = assess_preparation(
        manifest=_manifest(supported=False),
        inventory={**_inventory(), "missing": [{"area": "auth", "detail": "api key"}]},
        endpoint_texts=[],
        plan=NormalizationPlan(notebook_url=""),
    )

    md = render_markdown(report)

    assert "# Preparation Readiness Report" in md
    assert "Overall status: `blocked`" in md
    assert "## Sources" in md
    assert "## Extraction" in md
    assert "Suggested action" in md
