from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.agentcli.assemble import AssembleInputError, run_assemble_pipeline
from loop_apidoc.agentcli import evidence as evidence_module
from loop_apidoc.agentcli.evidence import verify_extraction_evidence
from loop_apidoc.agentcli.verify import verify_extraction_dir
from loop_apidoc.domain.evidence import fragment_digest
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.shadow import bridge as bridge_module
from loop_apidoc.shadow.models import ArchitectureMode
from loop_apidoc.source_facts.collect import collect_facts
from tests.source_quality_support import write_passing_source_quality


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


def test_exact_evidence_verifier_materializes_every_reference_in_one_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verification must read the sources once, not once per reference.

    Counted, not timed. The timed version compared wall clock between a
    250-reference and a 1,000-reference run, which measures the machine as much
    as the algorithm — the sibling test written the same way failed under load
    while the code was unchanged, taking the whole quality gate with it (#120).

    What keeps this near-linear is that `verify_extraction_evidence` collects
    every declared reference into one deduplicated request set and calls
    `acquire_fragment_bundle` exactly once. Both halves are asserted: one call
    at each size, and a request set matching the distinct references rather
    than multiplying with them.
    """

    def build_case(name: str, count: int):
        sources = tmp_path / name
        sources.mkdir()
        lines = [f"evidence line {index}" for index in range(count)]
        (sources / "manual.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        manifest = build_manifest(sources_root=sources, urls=[], generated_at=NOW)
        facts = collect_facts(sources, manifest)
        inventory = {
            "endpoints": [
                {
                    "evidence": [
                        {
                            "version": 1,
                            "source": "manual.md",
                            "locator": {
                                "kind": "line_range",
                                "start_line": index + 1,
                                "end_line": index + 1,
                            },
                            "fragment_digest": fragment_digest(line),
                            "claim_path": "/summary",
                        }
                        for index, line in enumerate(lines)
                    ]
                }
            ]
        }
        return inventory, manifest, facts

    requested: list[int] = []
    original = evidence_module.acquire_fragment_bundle

    def counting(source_set, manifest, facts, requests, generated_at):
        requested.append(len(requests))
        return original(source_set, manifest, facts, requests, generated_at)

    monkeypatch.setattr(evidence_module, "acquire_fragment_bundle", counting)

    for name, count in (("small", 250), ("large", 1_000)):
        requested.clear()
        inventory, manifest, facts = build_case(name, count)
        assert verify_extraction_evidence(
            inventory,
            [],
            None,
            manifest,
            facts,
            NOW,
        ) == []
        assert requested == [count], (
            f"{name}: expected one materialization of {count} distinct requests, "
            f"got {requested}"
        )


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


def test_domain_semantic_exact_evidence_is_verified(tmp_path):
    sources, _manifest, _facts = _sources_and_manifest(tmp_path)
    extraction = tmp_path / "extraction"
    _write_extraction(extraction, _inventory())
    (extraction / "integration.json").write_text(
        json.dumps(
            {
                "line_currency_policy": [
                    {
                        "scope": "Agent line",
                        "policy": "single",
                        "source": "manual.md line 4",
                        "evidence": [
                            _reference(digest="a" * 64)
                            | {"claim_path": "/policy"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    violations = verify_extraction_dir(
        sources_root=sources,
        extraction_dir=extraction,
        generated_at=NOW,
    )

    assert any("fragment_digest is stale or mismatched" in item for item in violations)


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
            source_quality_dir=write_passing_source_quality(
                sources_root=sources,
                output=tmp_path / "source-quality",
                generated_at=NOW,
            ),
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
        source_quality_dir=write_passing_source_quality(
            sources_root=sources,
            output=tmp_path / "source-quality",
            generated_at=NOW,
        ),
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


def test_shadow_assembly_does_no_linear_fragment_scan_per_exact_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shadow lookup must not walk the fragment list once per exact reference.

    Counted, not timed. The previous version compared wall clock between a
    200-reference and a 1,600-reference run; under load it failed while the
    code was unchanged and took the whole quality gate down with it (#120). The
    ratio was also a weak bound — it tolerated an 8x input growing 10x in time,
    most of the way to the quadratic blow-up it was written to catch.

    `_BridgeLookup.fragment_by_id` is the single per-proposal fragment lookup
    and a dict read, so the measured quantity is how often the shadow path
    resolves a fragment at all. Measured, that count is *constant* — driven by
    material claim paths, not by references — which is pinned here by equality.
    A change that makes it grow with the references is not necessarily wrong,
    but it is exactly the kind of change that should have to say so out loud.

    The second assertion guards the original defect: this lookup replaced a
    `for fragment in evidence.fragments` scan that ran inside a per-path,
    per-proposal `any(...)`, so every one of those calls walked the whole
    fragment list. Asserting the helper is gone keeps it from reappearing.
    """

    def lookups_for(count: int) -> int:
        case_root = tmp_path / f"case-{count}"
        sources = case_root / "sources"
        extraction = case_root / "extraction"
        sources.mkdir(parents=True)
        lines = ["# Demo API", "GET", "/ping", "Ping"] + [
            f"evidence line {index}" for index in range(count - 1)
        ]
        (sources / "manual.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        evidence = [
            {
                "version": 1,
                "source": "manual.md",
                "locator": {
                    "kind": "line_range",
                    "start_line": index + 4,
                    "end_line": index + 4,
                },
                "fragment_digest": fragment_digest(line),
                "claim_path": "/summary",
            }
            for index, line in enumerate(lines[3:])
        ]
        _write_extraction(extraction, _inventory(evidence=evidence))

        calls = 0
        original = bridge_module._BridgeLookup.fragment_by_id

        def counting(self, fragment_id):
            nonlocal calls
            calls += 1
            return original(self, fragment_id)

        monkeypatch.setattr(bridge_module._BridgeLookup, "fragment_by_id", counting)
        result = run_assemble_pipeline(
            sources_root=sources,
            extraction_dir=extraction,
            output_root=case_root / "output",
            run_id=f"shadow-{count}",
            generated_at=NOW,
            source_quality_dir=write_passing_source_quality(
                sources_root=sources,
                output=case_root / "source-quality",
                generated_at=NOW,
            ),
            architecture_mode=ArchitectureMode.SHADOW,
        )
        assert result.shadow is not None
        assert result.shadow.status == "ok"
        return calls

    small_lookups = lookups_for(200)
    large_lookups = lookups_for(1_600)

    assert small_lookups > 0, "the per-proposal lookup seam was not exercised"
    assert large_lookups == small_lookups, (
        "8x more exact references changed how often the shadow path resolves a "
        "fragment; it is driven by claim paths, not by reference count "
        f"(small={small_lookups}, large={large_lookups})"
    )

    assert not hasattr(bridge_module, "_fragment_index"), (
        "a linear scan over evidence.fragments reappeared beside the dict lookup; "
        "resolve a fragment by id through _BridgeLookup instead"
    )
