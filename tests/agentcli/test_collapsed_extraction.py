from __future__ import annotations

import json
from pathlib import Path

from loop_apidoc.agentcli.extraction import (
    INVENTORY_PROMPT,
    inventory_to_stage_answers,
    run_agent_extraction,
)
from loop_apidoc.extraction.jsonblock import extract_json_block
from loop_apidoc.extraction.store import ExtractionStore

_INVENTORY = {
    "overview": "A payments API.",
    "environments": [{"name": "prod", "base_url": "https://api", "version": "v1",
                      "source": "p.1"}],
    "security_schemes": [{"name": "AES", "type": None, "location": None,
                          "details": None, "source": "p.2"}],
    "endpoints": [{"method": "POST", "path": "/pay", "summary": "pay",
                   "source": "p.3"}],
    "schemas": [],
    "errors": [{"code": "E1", "meaning": "bad", "http_status": "400", "source": "p.9"}],
    "operational": [{"topic": "rate", "detail": "100/m", "source": "p.10"}],
    "missing": ["webhooks"],
}

_ENDPOINT_DETAIL = json.dumps({
    "method": "POST", "path": "/pay",
    "parameters": [{"name": "amount", "in": "body", "type": "int",
                    "required": True, "description": "amount"}],
    "request": None,
    "responses": [{"status": "200", "description": "ok", "schema": None}],
    "examples": [], "missing": [],
})


class _FakeResult:
    def __init__(self, answer: str) -> None:
        self.answer = answer


class _FakeAdapter:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def ask(self, question: str, notebook_url: str = "") -> _FakeResult:
        self.questions.append(question)
        if question == INVENTORY_PROMPT:
            return _FakeResult("```json\n" + json.dumps(_INVENTORY) + "\n```")
        return _FakeResult(_ENDPOINT_DETAIL)


def test_inventory_split_maps_each_stage():
    answers = inventory_to_stage_answers(_INVENTORY)
    assert "A payments API." in answers["02"]  # overview narrative
    assert extract_json_block(answers["03"])["environments"][0]["base_url"] == "https://api"
    assert extract_json_block(answers["04"])["security_schemes"][0]["name"] == "AES"
    assert extract_json_block(answers["05"])["endpoints"][0]["path"] == "/pay"
    assert extract_json_block(answers["08"])["errors"][0]["code"] == "E1"
    assert extract_json_block(answers["09"])["operational"][0]["topic"] == "rate"
    assert "webhooks" in answers["10"]  # gaps surfaced


def test_run_agent_extraction_fans_out_and_persists(tmp_path: Path):
    store = ExtractionStore(tmp_path)
    adapter = _FakeAdapter()
    result = run_agent_extraction(adapter, store)

    ids = {a.query_id for a in result.artifacts}
    assert {"02-initial", "03-initial", "05-initial", "08-initial"} <= ids
    assert "06-ep0" in ids  # one endpoint -> one detail query
    # one inventory query + one per-endpoint query
    assert adapter.questions[0] == INVENTORY_PROMPT
    assert sum("integration details" in q for q in adapter.questions) == 1
    # artifacts persisted to disk
    assert (tmp_path / "answers" / "06-ep0.txt").exists()


def test_run_agent_extraction_feeds_plan_builder(tmp_path: Path):
    from loop_apidoc.manifest.models import (
        LocalSource,
        Manifest,
        ProcessingStatus,
        SourceFormat,
    )
    from loop_apidoc.plan.builder import build_normalization_plan
    from datetime import datetime, timezone

    now = datetime(2026, 6, 27, tzinfo=timezone.utc)
    manifest = Manifest(
        sources_root="/s", generated_at=now,
        local_sources=[LocalSource(
            relative_path="m.pdf", mime_type="application/pdf",
            source_format=SourceFormat.PDF, size_bytes=1, sha256="x",
            scanned_at=now, supported=True, status=ProcessingStatus.PENDING)],
    )
    store = ExtractionStore(tmp_path)
    extraction = run_agent_extraction(_FakeAdapter(), store)
    plan = build_normalization_plan(extraction, manifest)

    assert len(plan.endpoints) == 1
    ep = plan.endpoints[0]
    assert ep.path == "/pay"
    assert ep.responses == [{"status": "200", "description": "ok", "schema": None}]
    assert plan.environments[0].base_url == "https://api"
    assert plan.errors[0].code == "E1"
