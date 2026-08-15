from __future__ import annotations

from loop_apidoc.source_facts.models import (
    EndpointFact,
    ErrorCodeFact,
    FactIndex,
    SourceFacts,
    TableCellFact,
    TableFact,
)


def _endpoint(path: str, value: object) -> EndpointFact:
    cell = TableCellFact(
        locator={
            "table_index": 0,
            "row_index": 0,
            "column_index": 0,
            "column_name": "Required",
        },
        line=4,
        normalized_excerpt=str(value),
        semantic_value=value,
    )
    return EndpointFact(
        relative_path="doc.md",
        heading=path,
        method="POST",
        path=path,
        line=1,
        tables=(
            TableFact(
                table_index=0,
                start_line=2,
                end_line=4,
                headers=("Required",),
                rows=((cell,),),
            ),
        ),
    )


def test_duplicate_endpoint_intersection_keeps_shared_exact_cells():
    index = FactIndex(
        sources=[
            SourceFacts(relative_path="a.md", endpoints=[_endpoint("/pay", True)]),
            SourceFacts(relative_path="b.md", endpoints=[_endpoint("/pay", True)]),
        ]
    )

    merged = index.by_identity()[("POST", "/pay")]

    assert merged.tables[0].rows[0][0].semantic_value is True


def test_duplicate_endpoint_intersection_drops_incompatible_exact_cells():
    index = FactIndex(
        sources=[
            SourceFacts(relative_path="a.md", endpoints=[_endpoint("/pay", True)]),
            SourceFacts(relative_path="b.md", endpoints=[_endpoint("/pay", False)]),
        ]
    )

    merged = index.by_identity()[("POST", "/pay")]

    assert merged.tables == ()


def _error_code(code: str, line: int, path: str = "manual.md") -> ErrorCodeFact:
    return ErrorCodeFact(
        relative_path=path,
        code=code,
        line=line,
        table_index=0,
        row_index=0,
        column_index=0,
        column_name="錯誤碼",
        normalized_excerpt=f"| {code} | 說明 |",
    )


def test_documented_error_codes_unions_across_sources() -> None:
    """跨來源取聯集,與端點的 by_identity() 交集刻意相反。

    兩份文件的錯誤碼表通常記載的是不同的碼集,而不是同一件事的兩種說法;
    取交集會把只出現在其中一份的碼全部丟掉,下界近乎歸零。
    """
    index = FactIndex(sources=[
        SourceFacts(relative_path="manual.md", error_codes=[
            _error_code("1001", 10), _error_code("1002", 11)]),
        SourceFacts(relative_path="errors.md", error_codes=[
            _error_code("1002", 5, "errors.md"), _error_code("2001", 6, "errors.md")]),
    ])

    floor = index.documented_error_codes()

    assert sorted(floor) == ["1001", "1002", "2001"]


def test_a_code_documented_twice_keeps_both_locations() -> None:
    """罰單要指出漏掉的碼寫在哪裡,所以每個記載位置都要留著。"""
    index = FactIndex(sources=[
        SourceFacts(relative_path="manual.md", error_codes=[_error_code("1002", 11)]),
        SourceFacts(relative_path="errors.md", error_codes=[_error_code("1002", 5, "errors.md")]),
    ])

    assert [(fact.relative_path, fact.line)
            for fact in index.documented_error_codes()["1002"]] == [
        ("manual.md", 11), ("errors.md", 5)]


def test_a_source_without_error_codes_contributes_nothing() -> None:
    index = FactIndex(sources=[SourceFacts(relative_path="manual.md")])

    assert index.documented_error_codes() == {}
