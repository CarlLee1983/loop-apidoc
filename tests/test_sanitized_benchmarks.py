from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.agentcli.assemble import run_assemble_pipeline
from loop_apidoc.shadow.models import ArchitectureMode
from scripts.quality_gate import required_sanitized_benchmark_cases


ROOT = Path(__file__).resolve().parents[1]
FIXED_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize("case_id", required_sanitized_benchmark_cases())
def test_sanitized_fixture_proves_fixture_backed_exact_evidence_parity(
    case_id: str,
    tmp_path: Path,
) -> None:
    case = ROOT / "benchmarks" / case_id
    descriptor = json.loads(
        (case / "sanitized-fixture.json").read_text(encoding="utf-8")
    )
    assert descriptor["schema_version"] == 1
    assert descriptor["case_id"] == case_id
    assert descriptor["assurance"] == "sanitized_fixture_exact_evidence"
    assert descriptor["strict_local_eligible"] is False

    source = case / descriptor["sanitized_source"]["path"]
    content = source.read_bytes()
    assert hashlib.sha256(content).hexdigest() == descriptor["sanitized_source"]["sha256"]

    lines = content.decode("utf-8").splitlines()
    assert len(lines) == descriptor["sanitization"]["original_line_count"]
    retained = {
        line_number
        for start, end in descriptor["sanitization"]["retained_line_ranges"]
        for line_number in range(start, end + 1)
    }
    assert {
        index for index, line in enumerate(lines, start=1) if line
    } <= retained

    result = run_assemble_pipeline(
        sources_root=source.parent,
        extraction_dir=case / "extraction",
        output_root=tmp_path,
        run_id="sanitized-fixture",
        generated_at=FIXED_TS,
        architecture_mode=ArchitectureMode.SHADOW,
    )
    run_dir = Path(result.run_dir)
    comparison = json.loads(
        (run_dir / "core" / "comparison.json").read_text(encoding="utf-8")
    )
    relationships = json.loads(
        (run_dir / "core" / "relationships.json").read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (run_dir / "core" / "evidence.json").read_text(encoding="utf-8")
    )
    precision_by_id = {
        fragment["id"]: fragment["precision"]
        for fragment in evidence["fragments"]
    }

    assert comparison["legacy_status"] == "passed"
    assert comparison["core_verdict"] == "accept"
    assert comparison["verdict_match"] is True
    assert comparison["claim_counts"]["unverified"] == 0
    assert relationships
    assert all(
        relationship["relationship"] in {"explicit_support", "derived_support"}
        and precision_by_id[relationship["fragment_id"]] == "exact"
        and all(
            precision_by_id[fragment_id] == "exact"
            for fragment_id in relationship["context_fragment_ids"]
        )
        for relationship in relationships
    )
