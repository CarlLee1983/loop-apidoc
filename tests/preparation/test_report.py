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


def _manifest(
    *,
    supported: bool = True,
    relative_path: str = "manual.md",
    source_format: SourceFormat = SourceFormat.MARKDOWN,
) -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path=relative_path,
                mime_type="text/markdown",
                source_format=source_format,
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


def test_the_unsupported_warning_never_promises_a_conversion_preprocess_will_not_do():
    """`preprocess` 對 `.doc` 與試算表只做 byte-for-byte 複製。

    「Convert unsupported inputs during preprocess」比一句沒用的通則更糟:它指名
    了一個這條管線做不到的動作,而 operator 會照做並得到同一個檔案。這份報告
    每個 run 都會寫進去,是 operator 手上最早的四份說明之一。
    """
    report = assess_preparation(
        manifest=_manifest(
            supported=False,
            relative_path="codes.xlsx",
            source_format=SourceFormat.SPREADSHEET,
        ),
        inventory=_inventory(),
        endpoint_texts=[_endpoint()],
        plan=NormalizationPlan(notebook_url=""),
    )

    findings = [finding for phase in report.phases for finding in phase.findings]
    unsupported = [f for f in findings if f.summary == "unsupported source present"]
    assert len(unsupported) == 1
    assert unsupported[0].evidence == "codes.xlsx"
    assert "Markdown table" in unsupported[0].suggested_action
    assert "during preprocess" not in unsupported[0].suggested_action


def test_each_unsupported_source_gets_its_own_remedy():
    """兩種不支援的格式有兩個不同的下一步,合成一筆就必然講錯其中一個。"""
    manifest = _manifest(
        supported=False,
        relative_path="codes.xlsx",
        source_format=SourceFormat.SPREADSHEET,
    )
    manifest.local_sources.append(
        LocalSource(
            relative_path="spec.doc",
            mime_type="application/msword",
            size_bytes=12,
            sha256="def",
            scanned_at=_NOW,
            source_format=SourceFormat.WORD_LEGACY,
            supported=False,
            status=ProcessingStatus.UNSUPPORTED,
        )
    )

    report = assess_preparation(
        manifest=manifest,
        inventory=_inventory(),
        endpoint_texts=[_endpoint()],
        plan=NormalizationPlan(notebook_url=""),
    )

    findings = [finding for phase in report.phases for finding in phase.findings]
    unsupported = [f for f in findings if f.summary == "unsupported source present"]
    assert [f.evidence for f in unsupported] == ["codes.xlsx", "spec.doc"]
    assert "Markdown table" in unsupported[0].suggested_action
    assert ".docx" in unsupported[1].suggested_action


def test_plain_text_and_csv_get_their_own_remedy():
    """`.txt`／`.csv` 落到 UNKNOWN 只拿得到通則,現在各自具名(#113)。"""
    manifest = _manifest(
        supported=False,
        relative_path="notes.txt",
        source_format=SourceFormat.PLAIN_TEXT,
    )
    manifest.local_sources.append(
        LocalSource(
            relative_path="codes.csv",
            mime_type="text/csv",
            size_bytes=12,
            sha256="abc",
            scanned_at=_NOW,
            source_format=SourceFormat.CSV,
            supported=False,
            status=ProcessingStatus.UNSUPPORTED,
        )
    )

    report = assess_preparation(
        manifest=manifest,
        inventory=_inventory(),
        endpoint_texts=[_endpoint()],
        plan=NormalizationPlan(notebook_url=""),
    )

    findings = [finding for phase in report.phases for finding in phase.findings]
    unsupported = [f for f in findings if f.summary == "unsupported source present"]
    assert [f.evidence for f in unsupported] == ["notes.txt", "codes.csv"]
    assert ".md" in unsupported[0].suggested_action
    assert "Markdown" in unsupported[1].suggested_action
    # 試算表的 remedy 也含「Markdown」,單看這個詞分辨不出 CSV 有沒有被誤指到
    # 試算表那一筆——所以再斷言 CSV 自己的 remedy 以 CSV 為主詞。
    assert "csv" in unsupported[1].suggested_action.lower()
    assert "spreadsheet" not in unsupported[1].suggested_action.lower()


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
