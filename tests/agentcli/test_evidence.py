from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.agentcli.assemble import AssembleInputError, run_assemble_pipeline
from loop_apidoc.agentcli.evidence import verify_extraction_evidence
from loop_apidoc.agentcli.verify import verify_extraction_dir
from loop_apidoc.domain.evidence import fragment_digest
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.shadow.models import ArchitectureMode
from loop_apidoc.source_facts.collect import collect_facts


NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)
_SOURCE = "# Demo API\nGET\n/ping\nPing\n"


def _reference(*, digest: str | None = None, source: str = "manual.md") -> dict:
    return {
        "version": 1,
        "source": source,
        "locator": {"kind": "line_range", "start_line": 4, "end_line": 4},
        "fragment_digest": digest or fragment_digest("Ping"),
        "claim_path": "/summary",
    }


def _inventory(*, evidence: list[dict] | None = None) -> dict:
    return {
        "title": "Demo API",
        "version": "1",
        "overview": "Demo API",
        "environments": [
            {
                "name": "prod",
                "base_url": "https://api.example.com",
                "version": "1",
                "source": "manual.md lines 1-4",
            }
        ],
        "security_schemes": [],
        "endpoints": [
            {
                "method": "GET",
                "path": "/ping",
                "summary": "Ping",
                "source": "manual.md lines 2-4",
                "evidence": evidence or [_reference()],
            }
        ],
        "schemas": [],
        "errors": [],
        "operational": [],
        "missing": [],
    }


_ENDPOINT = {
    "method": "GET",
    "path": "/ping",
    "summary": "Ping",
    "source": "manual.md lines 2-4",
    "parameters": [],
    "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "tags": [],
    "security": [],
    "examples": [],
    "missing": [],
}


def _sources_and_manifest(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "manual.md").write_text(_SOURCE, encoding="utf-8")
    manifest = build_manifest(sources_root=sources, urls=[], generated_at=NOW)
    return sources, manifest, collect_facts(sources, manifest)


def _write_extraction(extraction: Path, inventory: dict) -> None:
    (extraction / "endpoints").mkdir(parents=True)
    (extraction / "inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8"
    )
    (extraction / "endpoints" / "ep00.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8"
    )


def test_exact_evidence_verifier_accepts_matching_fragment(tmp_path):
    _sources, manifest, facts = _sources_and_manifest(tmp_path)

    assert verify_extraction_evidence(
        _inventory(), [("ep00.json", _ENDPOINT)], None, manifest, facts, NOW
    ) == []


def test_exact_evidence_verifier_reports_stale_digest_and_unknown_source(tmp_path):
    _sources, manifest, facts = _sources_and_manifest(tmp_path)
    inventory = _inventory(evidence=[
        _reference(digest="a" * 64),
        _reference(source="missing.md"),
    ])

    violations = verify_extraction_evidence(
        inventory, [("ep00.json", _ENDPOINT)], None, manifest, facts, NOW
    )

    assert any("fragment_digest is stale or mismatched" in item for item in violations)
    assert any("missing.md" in item and "not a usable" in item for item in violations)


def test_verify_extraction_runs_exact_evidence_gate_without_writing(tmp_path):
    sources, _manifest, _facts = _sources_and_manifest(tmp_path)
    extraction = tmp_path / "extraction"
    _write_extraction(extraction, _inventory(evidence=[_reference(digest="a" * 64)]))

    violations = verify_extraction_dir(
        sources_root=sources,
        extraction_dir=extraction,
        generated_at=NOW,
    )

    assert any("fragment_digest is stale or mismatched" in item for item in violations)
    assert {path.name for path in tmp_path.iterdir()} == {"sources", "extraction"}


def test_verify_extraction_rejects_unmatched_exact_evidence_claim_path(tmp_path):
    sources, _manifest, _facts = _sources_and_manifest(tmp_path)
    extraction = tmp_path / "extraction"
    _write_extraction(
        extraction,
        _inventory(evidence=[_reference() | {"claim_path": "/not-a-claim"}]),
    )

    violations = verify_extraction_dir(
        sources_root=sources,
        extraction_dir=extraction,
        generated_at=NOW,
    )

    assert any("does not resolve to a material operation claim path" in item
               for item in violations)
    assert {path.name for path in tmp_path.iterdir()} == {"sources", "extraction"}


def test_assemble_rejects_stale_exact_evidence_before_run_directory(tmp_path):
    sources, _manifest, _facts = _sources_and_manifest(tmp_path)
    extraction = tmp_path / "extraction"
    _write_extraction(extraction, _inventory(evidence=[_reference(digest="a" * 64)]))

    with pytest.raises(AssembleInputError, match="fragment_digest is stale"):
        run_assemble_pipeline(
            sources_root=sources,
            extraction_dir=extraction,
            output_root=tmp_path / "output",
            run_id="stale-evidence",
            generated_at=NOW,
        )

    assert not (tmp_path / "output" / "stale-evidence").exists()


def test_shadow_uses_verified_v1_evidence_for_its_declared_claim_path(tmp_path):
    sources, _manifest, _facts = _sources_and_manifest(tmp_path)
    extraction = tmp_path / "extraction"
    _write_extraction(extraction, _inventory())

    result = run_assemble_pipeline(
        sources_root=sources,
        extraction_dir=extraction,
        output_root=tmp_path / "output",
        run_id="exact-evidence",
        generated_at=NOW,
        architecture_mode=ArchitectureMode.SHADOW,
    )

    assert result.shadow is not None
    assert result.shadow.status == "ok"
    relationships = json.loads(
        (Path(result.run_dir) / "core" / "relationships.json").read_text(
            encoding="utf-8"
        )
    )
    summary = [
        item
        for item in relationships
        if item["claim_path"] == "/summary"
        and item["relationship"] == "explicit_support"
    ]
    assert len(summary) == 1
    assert summary[0]["reason_code"] == "CLAIM_BOUND_EXACT_REFERENCE"
