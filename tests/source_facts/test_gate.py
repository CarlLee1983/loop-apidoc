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


def _facts_in(path: str, *facts: EndpointFact) -> SourceFacts:
    return SourceFacts(relative_path=path, endpoints=list(facts))


def test_conflicting_sources_for_one_endpoint_require_only_their_intersection() -> None:
    """同一端點被兩處描述時(v1 已棄用 / 總覽索引頁 vs 細節頁),取「最豐富的」
    會要求擷取去滿足它本來就該忽略的那一節。歧義時 fail open 才是對的偏誤。"""
    index = FactIndex(sources=[
        _facts_in("overview.md", EndpointFact(
            relative_path="overview.md", heading="API list", method="POST",
            path="/transfer", line=1, parameter_names=["oldA", "oldB", "amount"],
            example_blocks=2)),
        _facts_in("detail.md", EndpointFact(
            relative_path="detail.md", heading="Transfer", method="POST",
            path="/transfer", line=1, parameter_names=["amount"], example_blocks=0)),
    ])
    endpoints = [(
        "ep1.json",
        {"method": "POST", "path": "/transfer",
         "parameters": [{"name": "amount"}], "examples": []},
    )]
    assert source_fact_violations(index, endpoints) == []


def test_a_single_source_endpoint_keeps_its_full_requirement() -> None:
    index = FactIndex(sources=[_facts_in("detail.md", EndpointFact(
        relative_path="detail.md", heading="Transfer", method="POST", path="/transfer",
        line=1, parameter_names=["amount", "currency"], example_blocks=0))])
    endpoints = [(
        "ep1.json",
        {"method": "POST", "path": "/transfer", "parameters": [{"name": "amount"}]},
    )]
    assert "currency" in source_fact_violations(index, endpoints)[0]


def test_error_fields_recorded_in_the_inventory_error_catalog_are_accounted_for() -> None:
    """付款/遊戲類文件幾乎都把錯誤表在每個端點重複一次,而正確的擷取會把它
    收在 inventory.errors[] 一處。看不到那裡就會逐個端點誤擋。"""
    inventory = {"errors": [
        {"code": "400", "fields": [{"name": "error_code"}, {"name": "error_msg"}]}
    ]}
    fact = _fact(parameter_names=["X-Token", "provider", "error_code", "error_msg"])
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "X-Token"}, {"name": "provider"}],
            "responses": [{"status": "400", "description": "Error."}],
            "examples": [{"body": "{}"}],
        },
    )]
    assert source_fact_violations(_index(fact), endpoints, inventory) == []


def test_a_schema_named_as_a_plain_string_resolves_like_a_ref() -> None:
    """ResponseEntry.schema 依設計是自由格式,直接寫共用 schema 名是合法的。"""
    inventory = {"schemas": [{"name": "Envelope", "fields": [{"name": "provider"}]}]}
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "parameters": [{"name": "X-Token"}],
            "responses": [{"status": "200", "description": "ok", "schema": "Envelope"}],
            "examples": [{"body": "{}"}],
        },
    )]
    assert source_fact_violations(_index(_fact()), endpoints, inventory) == []
