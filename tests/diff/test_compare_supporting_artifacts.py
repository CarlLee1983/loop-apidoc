from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.diff.compare import build_diff_report
from loop_apidoc.diff.loader import RunArtifacts
from loop_apidoc.diff.models import DiffImpact
from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.preparation.models import PreparationReport, PreparationStatus
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport

_NOW = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1.0.0"},
        "paths": {},
    }


def _manifest(sha256: str = "abc") -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=10,
                sha256=sha256,
                scanned_at=_NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )


def _artifacts(**overrides) -> RunArtifacts:
    base = RunArtifacts(
        run_dir=Path(overrides.pop("run_name", "run")),
        openapi=_openapi(),
        integration=None,
        provenance=ProvenanceDocument(notebook_url="", entries=[]),
        validation=ValidationReport(),
        manifest=_manifest(),
    )
    return replace(base, **overrides)


def _find(text: str, findings):
    return [finding for finding in findings if text in finding.summary][0]


def test_integration_crypto_algorithm_change_is_breaking():
    base = _artifacts(
        integration={"crypto": [{"name": "TradeInfo", "algorithm": "AES-256-CBC"}]}
    )
    head = _artifacts(
        integration={"crypto": [{"name": "TradeInfo", "algorithm": "AES-256-GCM"}]}
    )

    report = build_diff_report(base, head)
    finding = _find("integration crypto core field changed", report.findings)

    assert finding.impact is DiffImpact.BREAKING
    assert finding.location == "integration.crypto.TradeInfo.algorithm"


def test_integration_callback_detail_change_is_changed():
    base = _artifacts(
        integration={"callbacks": [{"name": "notify", "transport": "POST"}]}
    )
    head = _artifacts(
        integration={"callbacks": [{"name": "notify", "transport": "HTTPS POST"}]}
    )

    report = build_diff_report(base, head)
    finding = _find("integration callback field changed", report.findings)

    assert finding.impact is DiffImpact.CHANGED
    assert finding.location == "integration.callbacks.notify.transport"


def test_integration_item_added_is_additive_and_removed_is_breaking():
    base = _artifacts(integration={"crypto": [{"name": "sig"}]})
    head = _artifacts(integration={"crypto": [{"name": "sig"}, {"name": "encrypt"}]})
    added = _find("integration crypto added", build_diff_report(base, head).findings)
    removed = _find("integration crypto removed", build_diff_report(head, base).findings)

    assert added.impact is DiffImpact.ADDITIVE
    assert removed.impact is DiffImpact.BREAKING


def test_provenance_citation_change_is_source_only():
    base = _artifacts(
        provenance=ProvenanceDocument(
            notebook_url="",
            entries=[
                ProvenanceEntry(
                    target="paths./payments.post",
                    status=PlanItemStatus.SUPPORTED,
                    manifest_source="manual-v1.md",
                    query_id="06",
                )
            ],
        )
    )
    head = _artifacts(
        provenance=ProvenanceDocument(
            notebook_url="",
            entries=[
                ProvenanceEntry(
                    target="paths./payments.post",
                    status=PlanItemStatus.SUPPORTED,
                    manifest_source="manual-v2.md",
                    query_id="06",
                )
            ],
        )
    )

    finding = _find("provenance changed", build_diff_report(base, head).findings)
    assert finding.impact is DiffImpact.SOURCE_ONLY


def test_provenance_entry_reorder_is_not_reported():
    first = ProvenanceEntry(
        target="paths./payments.post",
        status=PlanItemStatus.SUPPORTED,
        manifest_source="manual-v1.md",
        query_id="06",
    )
    second = ProvenanceEntry(
        target="paths./payments.post",
        status=PlanItemStatus.SUPPORTED,
        manifest_source="manual-v2.md",
        query_id="07",
    )
    base = _artifacts(
        provenance=ProvenanceDocument(notebook_url="", entries=[first, second])
    )
    head = _artifacts(
        provenance=ProvenanceDocument(notebook_url="", entries=[second, first])
    )

    report = build_diff_report(base, head)

    assert [
        finding for finding in report.findings if finding.area == "provenance"
    ] == []


def test_validation_issue_change_is_source_only():
    base = _artifacts(validation=ValidationReport())
    head = _artifacts(
        validation=ValidationReport(
            issues=[
                Issue(
                    code=IssueCode.REQUIRED_INFO_MISSING,
                    severity=Severity.WARNING,
                    location="operational",
                    evidence="no rate limit",
                    suggested_fix="add source",
                )
            ]
        )
    )

    finding = _find("validation issue added", build_diff_report(base, head).findings)
    assert finding.impact is DiffImpact.SOURCE_ONLY


def test_manifest_source_hash_change_is_source_only():
    base = _artifacts(manifest=_manifest("abc"))
    head = _artifacts(manifest=_manifest("def"))

    finding = _find("manifest source changed", build_diff_report(base, head).findings)
    assert finding.impact is DiffImpact.SOURCE_ONLY
    assert finding.location == "manifest.local.manual.md"


def _manifest_scanned(scanned_at: datetime) -> Manifest:
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
                scanned_at=scanned_at,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )


def test_manifest_scanned_at_only_change_is_not_reported():
    later = datetime(2026, 6, 30, 9, 0, tzinfo=timezone.utc)
    base = _artifacts(manifest=_manifest_scanned(_NOW))
    head = _artifacts(manifest=_manifest_scanned(later))

    findings = build_diff_report(base, head).findings
    assert not [f for f in findings if "manifest source changed" in f.summary]


def test_integration_unnamed_collision_removal_is_reported():
    base = _artifacts(
        integration={
            "crypto": [
                {"purpose": "encrypt", "algorithm": "AES"},
                {"purpose": "encrypt", "algorithm": "AES"},
            ]
        }
    )
    head = _artifacts(
        integration={"crypto": [{"purpose": "encrypt", "algorithm": "AES"}]}
    )

    finding = _find("integration crypto removed", build_diff_report(base, head).findings)
    assert finding.impact is DiffImpact.BREAKING


def test_validation_issue_suggested_fix_change_is_reported():
    issue = dict(
        code=IssueCode.REQUIRED_INFO_MISSING,
        severity=Severity.WARNING,
        location="operational",
        evidence="no rate limit",
    )
    base = _artifacts(
        validation=ValidationReport(issues=[Issue(**issue, suggested_fix="add source A")])
    )
    head = _artifacts(
        validation=ValidationReport(issues=[Issue(**issue, suggested_fix="add source B")])
    )

    findings = build_diff_report(base, head).findings
    assert [f for f in findings if "validation issue" in f.summary]


def test_preparation_status_change_is_source_only():
    base = _artifacts(
        preparation=PreparationReport(
            status=PreparationStatus.READY,
            summary={"blocked": 0, "needs_attention": 0, "ready": 4},
        )
    )
    head = _artifacts(
        preparation=PreparationReport(
            status=PreparationStatus.BLOCKED,
            summary={"blocked": 1, "needs_attention": 3, "ready": 0},
        )
    )

    finding = _find("preparation status changed", build_diff_report(base, head).findings)

    assert finding.impact is DiffImpact.SOURCE_ONLY
    assert finding.location == "preparation.status"


def test_preparation_report_added_is_source_only():
    base = _artifacts(preparation=None)
    head = _artifacts(
        preparation=PreparationReport(
            status=PreparationStatus.READY,
            summary={"blocked": 0, "needs_attention": 0, "ready": 4},
        )
    )

    finding = _find("preparation report added", build_diff_report(base, head).findings)

    assert finding.impact is DiffImpact.SOURCE_ONLY
    assert finding.location == "preparation"
