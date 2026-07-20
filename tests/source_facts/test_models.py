from __future__ import annotations

from loop_apidoc.source_facts.models import (
    EndpointFact,
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
