from __future__ import annotations

import json

from loop_apidoc.plan.models import (
    EndpointEntry,
    NormalizationPlan,
    PlanItemStatus,
    SourceCitation,
)


def test_status_values():
    assert PlanItemStatus.SUPPORTED.value == "supported"
    assert PlanItemStatus.UNVERIFIED.value == "unverified"
    assert PlanItemStatus.MISSING.value == "missing"
    assert PlanItemStatus.CONFLICTING.value == "conflicting"


def test_endpoint_entry_defaults():
    entry = EndpointEntry(
        method="GET", path="/u", summary="s", status=PlanItemStatus.SUPPORTED,
        citations=[SourceCitation(query_id="05-initial", answer_path="answers/05-initial.txt",
                                  manifest_source="api.pdf", locator="api.pdf")],
    )
    assert entry.parameters == []
    assert entry.responses == []
    assert entry.citations[0].manifest_source == "api.pdf"


def test_plan_round_trips_json():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        overview_note="It is an API.",
        endpoints=[EndpointEntry(method="GET", path="/u", summary=None,
                                 status=PlanItemStatus.UNVERIFIED, citations=[])],
    )
    payload = plan.model_dump_json(indent=2)
    restored = NormalizationPlan.model_validate(json.loads(payload))
    assert restored.endpoints[0].status is PlanItemStatus.UNVERIFIED
    assert restored.notebook_url == "https://nb/x"
    assert restored.environments == []
