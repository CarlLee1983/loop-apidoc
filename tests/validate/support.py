"""最小的合法 plan / manifest,讓測試能直接打 `validate_outputs` 這個 seam。

放在 support 而不是某個測試檔裡,是為了讓解析器行為的釘死測試(壓平的 HTML 掃出
零事實)能在它自己的檔案裡順手驗證那件事在報告裡看得見 —— 行為與可見性連在一起讀。
"""
from __future__ import annotations

from datetime import datetime

from loop_apidoc.generate import build_result
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SecuritySchemeEntry,
    SourceCitation,
    SystemGroup,
)
from loop_apidoc.validate import validate_outputs
from loop_apidoc.validate.fact_coverage import FactCoverage
from loop_apidoc.validate.models import ValidationReport

NOW = datetime(2026, 8, 16, 12, 0, 0)


def citation() -> SourceCitation:
    return SourceCitation(query_id="06", answer_path="answers/06.txt",
                          manifest_source="api.md", locator="p.1")


def manifest(relative_path: str = "api.md") -> Manifest:
    return Manifest(
        sources_root="./sources", generated_at=NOW,
        local_sources=[LocalSource(
            relative_path=relative_path, mime_type="text/markdown",
            source_format=SourceFormat.MARKDOWN, size_bytes=10, sha256="abc",
            scanned_at=NOW, supported=True, status=ProcessingStatus.PENDING)])


def plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="https://nb/x",
        system_groups=[SystemGroup(name="Loop API")],
        overview_note="API。",
        environments=[EnvironmentEntry(
            status=PlanItemStatus.SUPPORTED, name="prod",
            base_url="https://api.example.com", version="2024-01",
            citations=[citation()])],
        security_schemes=[SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth", type="apiKey",
            location="header", details="X-API-Key", citations=[citation()])],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
            summary="List", responses=[{"status": "200", "description": "ok"}],
            examples=[{"body": "{}"}], citations=[citation()])],
        operational=[OperationalEntry(status=PlanItemStatus.SUPPORTED,
                                      topic="rate", detail="60/min",
                                      citations=[citation()])])


def report(
    coverage: dict[str, FactCoverage] | None,
    *,
    source: str = "api.md",
) -> ValidationReport:
    normalization_plan = plan()
    scanned = manifest(source)
    return validate_outputs(
        normalization_plan, build_result(normalization_plan, scanned), scanned,
        fact_coverage=coverage,
    )


def unscanned(validation: ValidationReport) -> list:
    return [
        issue for issue in validation.issues
        if issue.code.value == "SOURCE_FACTS_UNSCANNED"
    ]
