from loop_apidoc.generate.examples import build_examples
from loop_apidoc.generate.openapi import build_openapi
from loop_apidoc.plan.models import EndpointEntry, NormalizationPlan, SourceCitation


def _cite(src: str) -> SourceCitation:
    return SourceCitation(query_id="q", answer_path="a", manifest_source=src)


def test_two_source_operation_ids_unique_no_folder_collision():
    # 兩個來源各一個 POST /pay（summary 帶不同 operation code），openapi 不應碰撞，
    # examples 資料夾名隨 operationId 唯一。
    plan = NormalizationPlan(
        notebook_url="x",
        endpoints=[
            EndpointEntry(status="supported", method="POST", path="/a",
                summary="[NPA-F01] 付款", citations=[_cite("src1.pdf")]),
            EndpointEntry(status="supported", method="POST", path="/b",
                summary="[NPA-F02] 退款", citations=[_cite("src2.pdf")]),
        ],
    )
    openapi = build_openapi(plan)
    out = build_examples(openapi, plan)
    folders = {p.split("/")[1] for p in out if p != "examples/README.md"}
    assert len(folders) == 2  # 無碰撞


def test_two_source_missing_value_stays_placeholder():
    # 某端點欄位來源未給範例值 → 範例必為佔位，不得出現型別樣本。
    plan = NormalizationPlan(
        notebook_url="x",
        endpoints=[
            EndpointEntry(status="supported", method="POST", path="/pay",
                summary="付款",
                parameters=[{"name": "Amount", "in": "query", "schema": {"type": "integer"}}],
                citations=[_cite("src1.pdf")]),
        ],
    )
    openapi = build_openapi(plan)
    out = build_examples(openapi, plan)
    sh = next(v for k, v in out.items() if k.endswith("request.sh"))
    assert "Amount=<amount>" in sh
    assert "Amount=0" not in sh and "Amount=string" not in sh
