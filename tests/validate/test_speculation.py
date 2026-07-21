from __future__ import annotations

from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.validate.models import IssueCode
from loop_apidoc.validate.speculation import check_speculation

_OPENAPI = {
    "openapi": "3.1.0",
    "info": {"title": "X", "version": "1.0"},
    "paths": {"/users": {"get": {"responses": {"200": {"description": "ok"}}}}},
}


def _prov(*entries) -> ProvenanceDocument:
    return ProvenanceDocument(notebook_url="https://nb/x", entries=list(entries))


def _e(target, status) -> ProvenanceEntry:
    return ProvenanceEntry(target=target, status=status)


def _supported_prov() -> ProvenanceDocument:
    return _prov(
        _e("info.title", PlanItemStatus.SUPPORTED),
        _e("info.version", PlanItemStatus.SUPPORTED),
        _e("paths./users.get", PlanItemStatus.SUPPORTED),
    )


def test_all_supported_has_no_issues():
    assert check_speculation(_OPENAPI, _supported_prov()) == []


def test_missing_provenance_is_unsupported_assertion():
    prov = _prov(
        _e("info.title", PlanItemStatus.SUPPORTED),
        _e("info.version", PlanItemStatus.SUPPORTED),
    )  # no paths./users.get
    issues = check_speculation(_OPENAPI, prov)
    assert any(i.code is IssueCode.UNSUPPORTED_ASSERTION
               and i.location == "paths./users.get" for i in issues)


def test_conflicting_provenance_flagged():
    prov = _prov(
        _e("info.title", PlanItemStatus.SUPPORTED),
        _e("info.version", PlanItemStatus.SUPPORTED),
        _e("paths./users.get", PlanItemStatus.CONFLICTING),
    )
    issues = check_speculation(_OPENAPI, prov)
    assert any(i.code is IssueCode.SOURCE_CONFLICT
               and i.location == "paths./users.get" for i in issues)


def test_unverified_only_provenance_flagged():
    prov = _prov(
        _e("info.title", PlanItemStatus.SUPPORTED),
        _e("info.version", PlanItemStatus.SUPPORTED),
        _e("paths./users.get", PlanItemStatus.UNVERIFIED),
    )
    issues = check_speculation(_OPENAPI, prov)
    assert any(i.code is IssueCode.SOURCE_UNVERIFIED
               and i.location == "paths./users.get" for i in issues)


def test_missing_source_placeholder_is_skipped():
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "X", "version": "1.0"},
        "paths": {
            "/ping": {"get": {"responses": {
                "default": {"description": "x", "x-loop-status": "missing-source"}}}}
        },
        "components": {"securitySchemes": {
            "scheme0": {"type": "apiKey", "in": "header", "name": "A",
                        "x-loop-status": "missing-source"}}},
    }
    prov = _prov(
        _e("info.title", PlanItemStatus.SUPPORTED),
        _e("info.version", PlanItemStatus.SUPPORTED),
        _e("paths./ping.get", PlanItemStatus.SUPPORTED),
    )  # no provenance for scheme0 — but it is a missing-source placeholder
    issues = check_speculation(doc, prov)
    assert all("securitySchemes" not in i.location for i in issues)


def test_unverified_schema_property_provenance_overrides_supported_parent():
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "X", "version": "1.0"},
        "paths": {},
        "components": {"schemas": {
            "Order": {"type": "object", "properties": {
                "amount": {"type": "number"},
            }},
        }},
    }
    prov = _prov(
        _e("info.title", PlanItemStatus.SUPPORTED),
        _e("info.version", PlanItemStatus.SUPPORTED),
        _e("components.schemas.Order", PlanItemStatus.SUPPORTED),
        _e("components.schemas.Order.properties.amount", PlanItemStatus.UNVERIFIED),
    )

    issues = check_speculation(doc, prov)

    assert len(issues) == 1
    assert issues[0].code is IssueCode.SOURCE_UNVERIFIED
    assert issues[0].location == "components.schemas.Order.properties.amount"


def test_schema_property_without_provenance_uses_supported_parent_schema():
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "X", "version": "1.0"},
        "paths": {},
        "components": {"schemas": {
            "Order": {"type": "object", "properties": {
                "amount": {"type": "number"},
            }},
        }},
    }
    prov = _prov(
        _e("info.title", PlanItemStatus.SUPPORTED),
        _e("info.version", PlanItemStatus.SUPPORTED),
        _e("components.schemas.Order", PlanItemStatus.SUPPORTED),
    )

    issues = check_speculation(doc, prov)

    assert issues == []
