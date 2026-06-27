from __future__ import annotations

from loop_apidoc.agentcli.extraction import inventory_to_stage_answers
from loop_apidoc.extraction.jsonblock import extract_json_block

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


def test_inventory_split_maps_each_stage():
    answers = inventory_to_stage_answers(_INVENTORY)
    assert "A payments API." in answers["02"]
    assert extract_json_block(answers["03"])["environments"][0]["base_url"] == "https://api"
    assert extract_json_block(answers["04"])["security_schemes"][0]["name"] == "AES"
    assert extract_json_block(answers["05"])["endpoints"][0]["path"] == "/pay"
    assert extract_json_block(answers["08"])["errors"][0]["code"] == "E1"
    assert extract_json_block(answers["09"])["operational"][0]["topic"] == "rate"
    assert "webhooks" in answers["10"]


def test_title_surfaced_in_stage_00():
    answers = inventory_to_stage_answers({**_INVENTORY, "title": "Acme Pay API"})
    assert answers["00"] == "Acme Pay API"


def test_missing_title_yields_blank_stage_00():
    answers = inventory_to_stage_answers(_INVENTORY)
    assert answers["00"] == ""


def test_version_encoded_with_title_in_stage_00():
    answers = inventory_to_stage_answers(
        {**_INVENTORY, "title": "Acme Pay API", "version": "NDNF-1.2.2"})
    block = extract_json_block(answers["00"])
    assert block == {"title": "Acme Pay API", "version": "NDNF-1.2.2"}


def test_version_without_title_still_carried_in_stage_00():
    answers = inventory_to_stage_answers({**_INVENTORY, "version": "v3"})
    block = extract_json_block(answers["00"])
    assert block == {"title": None, "version": "v3"}


def test_global_missing_not_duplicated_into_every_inventory_stage():
    answers = inventory_to_stage_answers(_INVENTORY)
    for sid in ("03", "04", "05", "07", "08", "09"):
        assert "missing" not in extract_json_block(answers[sid])
    assert "webhooks" in answers["10"]
