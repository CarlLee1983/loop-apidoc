import json
from pathlib import Path

from loop_apidoc.agentcli.assemble import load_extraction_inputs


def _write(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_load_returns_integration_when_present(tmp_path: Path):
    _write(tmp_path / "inventory.json", {"title": "X", "overview": "o"})
    (tmp_path / "endpoints").mkdir()
    _write(tmp_path / "integration.json", {"crypto": [{"name": "c", "source": "s"}]})
    inventory, endpoint_texts, integration = load_extraction_inputs(tmp_path)
    assert integration["crypto"][0]["name"] == "c"


def test_load_integration_optional(tmp_path: Path):
    _write(tmp_path / "inventory.json", {"title": "X", "overview": "o"})
    (tmp_path / "endpoints").mkdir()
    inventory, endpoint_texts, integration = load_extraction_inputs(tmp_path)
    assert integration is None
