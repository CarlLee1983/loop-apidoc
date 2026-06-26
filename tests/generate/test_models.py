from __future__ import annotations

from loop_apidoc.generate.models import (
    GenerateResult,
    ProvenanceDocument,
    ProvenanceEntry,
)
from loop_apidoc.plan.models import PlanItemStatus


def test_provenance_entry_defaults():
    entry = ProvenanceEntry(target="info.title", status=PlanItemStatus.SUPPORTED)
    assert entry.manifest_source is None
    assert entry.query_id is None
    assert entry.answer_path is None
    assert entry.locator is None


def test_provenance_document_roundtrip():
    doc = ProvenanceDocument(
        notebook_url="https://nb/x",
        entries=[
            ProvenanceEntry(
                target="paths./users.get",
                status=PlanItemStatus.SUPPORTED,
                manifest_source="api.md",
                query_id="06-initial",
                answer_path="answers/06-initial.txt",
                locator="p.3",
            )
        ],
    )
    reloaded = ProvenanceDocument.model_validate_json(doc.model_dump_json())
    assert reloaded == doc
    assert reloaded.entries[0].status is PlanItemStatus.SUPPORTED


def test_generate_result_holds_three_artifacts():
    result = GenerateResult(
        openapi={"openapi": "3.1.0"},
        markdown="# x",
        provenance=ProvenanceDocument(notebook_url="https://nb/x"),
    )
    assert result.openapi["openapi"] == "3.1.0"
    assert result.markdown == "# x"
    assert result.provenance.notebook_url == "https://nb/x"
