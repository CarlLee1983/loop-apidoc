from __future__ import annotations

import json

from loop_apidoc.diff.findings import _finding, _sorted_findings, _summary
from loop_apidoc.diff.loader import RunArtifacts
from loop_apidoc.diff.models import DiffFinding, DiffImpact, DiffReport
from loop_apidoc.diff.openapi_compare import _compare_openapi


def _integration_items(integration: dict | None, section: str) -> dict[str, dict]:
    if not integration:
        return {}
    raw = integration.get(section)
    if not isinstance(raw, list):
        return {}
    out: dict[str, dict] = {}
    seen: dict[str, int] = {}
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        if section == "crypto":
            key = item.get("name") or f"{item.get('purpose', 'crypto')}:{item.get('algorithm', idx)}"
        elif section == "callbacks":
            key = item.get("name") or item.get("trigger") or str(idx)
        elif section == "field_conditions":
            key = f"{item.get('scope', idx)}:{item.get('when', '')}"
        elif section == "test_cases":
            key = item.get("name") or item.get("operation_ref") or str(idx)
        else:
            key = str(idx)
        key = str(key)
        # Unnamed items can collapse to the same fallback key (e.g. two crypto
        # blocks sharing purpose+algorithm). Suffix repeats with a stable
        # occurrence index so each is tracked separately instead of silently
        # overwriting the prior one.
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        out[f"{key}#{occurrence}" if occurrence else key] = item
    return out


def _compare_section_items(
    base: dict | None,
    head: dict | None,
    section: str,
    singular: str,
    core_fields: set[str],
) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_items = _integration_items(base, section)
    head_items = _integration_items(head, section)
    for key in sorted(head_items.keys() - base_items.keys()):
        findings.append(
            _finding(
                DiffImpact.ADDITIVE,
                "integration",
                f"integration.{section}.{key}",
                f"integration {singular} added",
                None,
                head_items[key],
            )
        )
    for key in sorted(base_items.keys() - head_items.keys()):
        findings.append(
            _finding(
                DiffImpact.BREAKING,
                "integration",
                f"integration.{section}.{key}",
                f"integration {singular} removed",
                base_items[key],
                None,
            )
        )
    for key in sorted(base_items.keys() & head_items.keys()):
        fields = sorted(set(base_items[key]) | set(head_items[key]))
        for field in fields:
            before = base_items[key].get(field)
            after = head_items[key].get(field)
            if before == after:
                continue
            impact = DiffImpact.BREAKING if field in core_fields else DiffImpact.CHANGED
            core = " core" if impact is DiffImpact.BREAKING else ""
            findings.append(
                _finding(
                    impact,
                    "integration",
                    f"integration.{section}.{key}.{field}",
                    f"integration {singular}{core} field changed",
                    before,
                    after,
                )
            )
    return findings


def _compare_integration(base: dict | None, head: dict | None) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    findings.extend(
        _compare_section_items(
            base,
            head,
            "crypto",
            "crypto",
            {"algorithm", "mode", "key_source", "payload_assembly", "verify"},
        )
    )
    findings.extend(
        _compare_section_items(
            base,
            head,
            "callbacks",
            "callback",
            {"verification", "expected_response"},
        )
    )
    findings.extend(
        _compare_section_items(
            base,
            head,
            "field_conditions",
            "field condition",
            {"then_required"},
        )
    )
    findings.extend(
        _compare_section_items(
            base,
            head,
            "test_cases",
            "test case",
            set(),
        )
    )
    return findings


def _provenance_map(artifacts: RunArtifacts) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for entry in artifacts.provenance.entries:
        out.setdefault(entry.target, []).append(entry.model_dump(mode="json"))
    for entries in out.values():
        entries.sort(
            key=lambda entry: (
                entry.get("manifest_source") or "",
                entry.get("query_id") or "",
                json.dumps(entry, sort_keys=True, separators=(",", ":")),
            )
        )
    return out


def _compare_provenance(base: RunArtifacts, head: RunArtifacts) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_entries = _provenance_map(base)
    head_entries = _provenance_map(head)
    for target in sorted(set(base_entries) | set(head_entries)):
        before = base_entries.get(target)
        after = head_entries.get(target)
        if before != after:
            findings.append(
                _finding(
                    DiffImpact.SOURCE_ONLY,
                    "provenance",
                    target,
                    "provenance changed",
                    before,
                    after,
                )
            )
    return findings


def _issue_key(issue) -> tuple[str, str, str, str, str]:
    # `suggested_fix` is part of the issue's identity here: changing only the
    # remediation text still alters validation/report.json, so it must shift the
    # key (surfacing as a removed+added pair) rather than diffing to nothing.
    return (
        issue.code.value,
        issue.severity.value,
        issue.location,
        issue.evidence,
        issue.suggested_fix,
    )


def _compare_validation(base: RunArtifacts, head: RunArtifacts) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_issues = {_issue_key(issue): issue for issue in base.validation.issues}
    head_issues = {_issue_key(issue): issue for issue in head.validation.issues}
    for key in sorted(head_issues.keys() - base_issues.keys()):
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "validation",
                f"validation.{key[0]}.{key[2]}",
                "validation issue added",
                None,
                head_issues[key].model_dump(mode="json"),
            )
        )
    for key in sorted(base_issues.keys() - head_issues.keys()):
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "validation",
                f"validation.{key[0]}.{key[2]}",
                "validation issue removed",
                base_issues[key].model_dump(mode="json"),
                None,
            )
        )
    return findings


def _manifest_local_map(artifacts: RunArtifacts) -> dict[str, dict]:
    # Exclude `scanned_at`: it changes on every rescan even when the source file
    # is byte-identical, which would flood a normal rerun diff with spurious
    # "manifest source changed" noise. Content identity lives in sha256/status.
    return {
        source.relative_path: source.model_dump(mode="json", exclude={"scanned_at"})
        for source in artifacts.manifest.local_sources
    }


def _manifest_url_map(artifacts: RunArtifacts) -> dict[str, dict]:
    # Same rationale as local sources: `fetched_at` is a rerun timestamp, not a
    # content signal (content_sha256/http_status carry that).
    return {
        source.citation_id: source.model_dump(mode="json", exclude={"fetched_at"})
        for source in artifacts.manifest.url_sources
    }


def _compare_manifest(base: RunArtifacts, head: RunArtifacts) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    for label, base_map, head_map in (
        ("local", _manifest_local_map(base), _manifest_local_map(head)),
        ("url", _manifest_url_map(base), _manifest_url_map(head)),
    ):
        for key in sorted(set(base_map) | set(head_map)):
            before = base_map.get(key)
            after = head_map.get(key)
            if before != after:
                findings.append(
                    _finding(
                        DiffImpact.SOURCE_ONLY,
                        "manifest",
                        f"manifest.{label}.{key}",
                        "manifest source changed",
                        before,
                        after,
                    )
                )
    return findings


def _preparation_phase_map(artifacts: RunArtifacts) -> dict[str, dict]:
    if artifacts.preparation is None:
        return {}
    return {
        phase.id: phase.model_dump(mode="json")
        for phase in artifacts.preparation.phases
    }


def _compare_preparation(base: RunArtifacts, head: RunArtifacts) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    if base.preparation is None and head.preparation is None:
        return findings
    if base.preparation is None:
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "preparation",
                "preparation",
                "preparation report added",
                None,
                head.preparation.model_dump(mode="json"),
            )
        )
        return findings
    if head.preparation is None:
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "preparation",
                "preparation",
                "preparation report removed",
                base.preparation.model_dump(mode="json"),
                None,
            )
        )
        return findings

    if base.preparation.status != head.preparation.status:
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "preparation",
                "preparation.status",
                "preparation status changed",
                base.preparation.status.value,
                head.preparation.status.value,
            )
        )
    if base.preparation.summary != head.preparation.summary:
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "preparation",
                "preparation.summary",
                "preparation summary changed",
                base.preparation.summary,
                head.preparation.summary,
            )
        )

    base_phases = _preparation_phase_map(base)
    head_phases = _preparation_phase_map(head)
    for phase_id in sorted(set(base_phases) | set(head_phases)):
        before = base_phases.get(phase_id)
        after = head_phases.get(phase_id)
        if before != after:
            findings.append(
                _finding(
                    DiffImpact.SOURCE_ONLY,
                    "preparation",
                    f"preparation.phases.{phase_id}",
                    "preparation phase changed",
                    before,
                    after,
                )
            )
    return findings


def build_diff_report(base: RunArtifacts, head: RunArtifacts) -> DiffReport:
    findings: list[DiffFinding] = []
    findings.extend(_compare_openapi(base.openapi, head.openapi))
    findings.extend(_compare_integration(base.integration, head.integration))
    findings.extend(_compare_provenance(base, head))
    findings.extend(_compare_validation(base, head))
    findings.extend(_compare_manifest(base, head))
    findings.extend(_compare_preparation(base, head))
    findings = _sorted_findings(findings)
    return DiffReport(
        base_run=str(base.run_dir),
        head_run=str(head.run_dir),
        summary=_summary(findings),
        findings=findings,
    )
