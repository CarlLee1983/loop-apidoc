"""語意完整性閘門:來源已機械證實存在的東西,擷取不得靜默消失。"""

from __future__ import annotations

from loop_apidoc.source_facts.gate import source_fact_violations
from loop_apidoc.source_facts.models import EndpointFact, FactIndex, SourceFacts


def _index(*facts: EndpointFact) -> FactIndex:
    return FactIndex(sources=[SourceFacts(relative_path="doc.md", endpoints=list(facts))])


def _fact(**kwargs) -> EndpointFact:
    base = dict(
        relative_path="doc.md", heading="H", method="GET", path="/games", line=1,
        parameter_names=["X-Token", "provider"], example_blocks=1,
    )
    return EndpointFact(**{**base, **kwargs})


def test_documented_parameter_table_must_not_yield_an_empty_parameter_list() -> None:
    endpoints = [("ep1.json", {"method": "GET", "path": "/games", "parameters": []})]
    violations = source_fact_violations(_index(_fact()), endpoints)
    assert any("X-Token" in v and "ep1.json" in v for v in violations)


def test_fully_extracted_endpoint_is_clean() -> None:
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "X-Token"}, {"name": "provider"}],
            "examples": [{"title": "ok", "body": "{}"}],
        },
    )]
    assert source_fact_violations(_index(_fact()), endpoints) == []


def test_partially_extracted_parameters_name_the_missing_fields() -> None:
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "X-Token"}],
            "examples": [{"body": "{}"}],
        },
    )]
    violations = source_fact_violations(_index(_fact()), endpoints)
    assert len(violations) == 1
    assert "provider" in violations[0]
    assert "X-Token" not in violations[0]


def test_a_declared_source_grounded_gap_accounts_for_a_missing_field() -> None:
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "X-Token"}],
            "examples": [{"body": "{}"}],
            "missing": ["The source table lists `provider` but never states its type."],
        },
    )]
    assert source_fact_violations(_index(_fact()), endpoints) == []


def test_field_names_are_found_in_request_and_response_schemas_too() -> None:
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "X-Token"}],
            "responses": [{"status": "200", "schema": {"properties": {"provider": {}}}}],
            "examples": [{"body": "{}"}],
        },
    )]
    assert source_fact_violations(_index(_fact()), endpoints) == []


def test_documented_examples_must_not_vanish() -> None:
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "X-Token"}, {"name": "provider"}],
            "examples": [],
        },
    )]
    violations = source_fact_violations(_index(_fact()), endpoints)
    assert len(violations) == 1
    assert "example" in violations[0].lower()


def test_no_source_example_means_no_example_requirement() -> None:
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "X-Token"}, {"name": "provider"}],
            "examples": [],
        },
    )]
    assert source_fact_violations(_index(_fact(example_blocks=0)), endpoints) == []


def test_endpoints_without_a_matching_source_fact_are_not_judged() -> None:
    endpoints = [("ep1.json", {"method": "POST", "path": "/unknown", "parameters": []})]
    assert source_fact_violations(_index(_fact()), endpoints) == []


def test_null_path_endpoints_are_not_judged() -> None:
    endpoints = [("ep1.json", {"method": "POST", "path": None, "parameters": []})]
    assert source_fact_violations(_index(_fact()), endpoints) == []


def test_an_empty_fact_index_never_blocks() -> None:
    endpoints = [("ep1.json", {"method": "GET", "path": "/games", "parameters": []})]
    assert source_fact_violations(FactIndex(), endpoints) == []


def test_fields_reached_through_a_schema_ref_are_accounted_for() -> None:
    """共用 schema 的欄位住在 inventory,端點只留一個 ref——不解析就會誤擋正確擷取。"""
    inventory = {
        "schemas": [
            {"name": "GameQuery", "fields": [{"name": "provider", "type": "string"}]}
        ]
    }
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "X-Token"}],
            "request": {"schema_ref": "GameQuery"},
            "examples": [{"body": "{}"}],
        },
    )]
    assert source_fact_violations(_index(_fact()), endpoints, inventory) == []


def test_a_schema_ref_that_does_not_carry_the_field_still_fails() -> None:
    inventory = {
        "schemas": [
            {"name": "GameQuery", "fields": [{"name": "unrelated", "type": "string"}]}
        ]
    }
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "X-Token"}],
            "request": {"schema_ref": "GameQuery"},
            "examples": [{"body": "{}"}],
        },
    )]
    violations = source_fact_violations(_index(_fact()), endpoints, inventory)
    assert "provider" in violations[0]


def test_nested_schema_refs_resolve_transitively() -> None:
    inventory = {
        "schemas": [
            {"name": "Outer", "fields": [{"name": "inner", "schema_ref": "Inner"}]},
            {"name": "Inner", "fields": [{"name": "provider", "type": "string"}]},
        ]
    }
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "X-Token"}],
            "responses": [{"status": "200", "schema_ref": "Outer"}],
            "examples": [{"body": "{}"}],
        },
    )]
    assert source_fact_violations(_index(_fact()), endpoints, inventory) == []


def test_a_self_referential_schema_does_not_hang() -> None:
    inventory = {
        "schemas": [{"name": "Loop", "fields": [{"name": "self", "schema_ref": "Loop"}]}]
    }
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "X-Token"}, {"name": "provider"}],
            "request": {"schema_ref": "Loop"},
            "examples": [{"body": "{}"}],
        },
    )]
    assert source_fact_violations(_index(_fact()), endpoints, inventory) == []


def test_a_dotted_source_path_is_satisfied_by_its_leaf_field() -> None:
    """來源把巢狀欄位寫成 `user.id`,擷取則是巢狀結構裡的 `id`——兩者是同一件事。"""
    fact = _fact(parameter_names=["user", "user.id"])
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "user"}],
            "request": {"schema": {"properties": {"user": {"properties": {"id": {}}}}}},
            "examples": [{"body": "{}"}],
        },
    )]
    assert source_fact_violations(_index(fact), endpoints) == []


def test_a_dotted_path_whose_leaf_is_absent_still_fails() -> None:
    fact = _fact(parameter_names=["user.id"])
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "user"}],
            "examples": [{"body": "{}"}],
        },
    )]
    assert "user.id" in source_fact_violations(_index(fact), endpoints)[0]
