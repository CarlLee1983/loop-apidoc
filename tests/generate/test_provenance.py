from __future__ import annotations

from loop_apidoc.generate.provenance import build_provenance
from loop_apidoc.plan.models import (
    ErrorEntry,
    EndpointEntry,
    EnvironmentEntry,
    MissingItem,
    NormalizationPlan,
    PlanItemStatus,
    SchemaEntry,
    SecuritySchemeEntry,
    SourceCitation,
    SourceConflict,
    SystemGroup,
    UnverifiedItem,
)


def _cite(**kw):
    return SourceCitation(query_id="q1", answer_path="answers/q1.txt", **kw)


def _targets(doc) -> dict[str, list]:
    out: dict[str, list] = {}
    for entry in doc.entries:
        out.setdefault(entry.target, []).append(entry)
    return out


def test_endpoint_target_and_citation():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[
            EndpointEntry(
                status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
                citations=[_cite(manifest_source="api.md", locator="p.2")],
            )
        ],
    )
    doc = build_provenance(plan)
    assert doc.notebook_url == "https://nb/x"
    entry = _targets(doc)["paths./users.get"][0]
    assert entry.status is PlanItemStatus.SUPPORTED
    assert entry.manifest_source == "api.md"
    assert entry.query_id == "q1"
    assert entry.answer_path == "answers/q1.txt"
    assert entry.locator == "p.2"


def test_info_targets_present():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        system_groups=[SystemGroup(name="API")],
        environments=[EnvironmentEntry(status=PlanItemStatus.SUPPORTED, version="1")],
    )
    targets = _targets(build_provenance(plan))
    assert "info.title" in targets
    assert "info.version" in targets


def test_info_missing_status_when_absent():
    targets = _targets(build_provenance(NormalizationPlan(notebook_url="https://nb/x")))
    assert targets["info.title"][0].status is PlanItemStatus.MISSING
    assert targets["info.version"][0].status is PlanItemStatus.MISSING


def test_server_target_indexed():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        environments=[
            EnvironmentEntry(
                status=PlanItemStatus.SUPPORTED, base_url="https://a",
                citations=[_cite(manifest_source="env.md")],
            )
        ],
    )
    assert "servers[0]" in _targets(build_provenance(plan))


def test_security_schema_error_operational_targets():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        security_schemes=[SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth",
            citations=[_cite()])],
        schemas=[SchemaEntry(status=PlanItemStatus.SUPPORTED, name="User",
                             citations=[_cite()])],
    )
    targets = _targets(build_provenance(plan))
    assert "components.securitySchemes.ApiKeyAuth" in targets
    assert "components.schemas.User" in targets


def test_missing_conflict_unverified_included():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        missing_items=[MissingItem(area="05", detail="no endpoints", query_id="05-initial")],
        source_conflicts=[SourceConflict(area="03", detail="two base urls")],
        unverified_items=[UnverifiedItem(area="06", detail="/x")],
    )
    targets = _targets(build_provenance(plan))
    assert targets["missing.05"][0].status is PlanItemStatus.MISSING
    assert targets["missing.05"][0].query_id == "05-initial"
    assert targets["conflict.03"][0].status is PlanItemStatus.CONFLICTING
    assert targets["unverified.06"][0].status is PlanItemStatus.UNVERIFIED


def test_endpoint_without_path_skipped_from_paths_target():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[EndpointEntry(status=PlanItemStatus.MISSING, method="GET", path=None,
                                 citations=[_cite()])],
    )
    assert not any(t.startswith("paths.") for t in _targets(build_provenance(plan)))


def test_named_enum_provenance_emitted_with_parent_schema_citation():
    """Named enums in schema.enums must produce their own provenance target (Fix 3)."""
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        schemas=[
            SchemaEntry(
                status=PlanItemStatus.SUPPORTED,
                name="Order",
                enums=[{"name": "OrderStatus", "values": ["new", "paid"]}],
                citations=[_cite(manifest_source="schema.md", locator="p.5")],
            )
        ],
    )
    targets = _targets(build_provenance(plan))
    assert "components.schemas.OrderStatus" in targets
    entry = targets["components.schemas.OrderStatus"][0]
    assert entry.status is PlanItemStatus.SUPPORTED
    assert entry.manifest_source == "schema.md"
    assert entry.query_id == "q1"


def test_error_code_component_mapping_has_source_provenance():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        errors=[ErrorEntry(
            status=PlanItemStatus.SUPPORTED,
            code="1001",
            meaning="Invalid token",
            citations=[_cite(manifest_source="errors.md", locator="#1001")],
        )],
    )

    targets = _targets(build_provenance(plan))

    assert targets["components.schemas.ErrorCode"][0].manifest_source == "errors.md"
    entry = targets["components.schemas.ErrorCode.1001"][0]
    assert entry.manifest_source == "errors.md"
    assert entry.locator == "#1001"
