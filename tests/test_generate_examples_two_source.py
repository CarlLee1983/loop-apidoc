from pathlib import Path

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
    folders = {Path(p).parts[1] for p in out if p != "examples/README.md"}
    assert len(folders) == 2  # 無碰撞
    # Lock the actual operationId folder names build_openapi produces.
    # [NPA-F01] → code "NPA-F01" → _ID_BAD strips "-" → "NPA_F01"
    # [NPA-F02] → code "NPA-F02" → _ID_BAD strips "-" → "NPA_F02"
    assert folders == {"NPA_F01", "NPA_F02"}


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


def test_two_source_missing_value_not_upgraded_by_other_source():
    # 跨源非升級：src1 有 Amount 的具體值；src2 的 Amount 無值。
    # src2 的 request.sh 必須是佔位 <amount>，不得繼承 src1 的值。
    #
    # 兩端點路徑不同（/a vs /b），確保是獨立 operation 而非合併。
    # 使用 schema.default 攜帶來源值；_build_parameter 保留 schema dict，
    # _resolve_value 從 schema["default"] 讀取 → ("source", 100)。
    plan = NormalizationPlan(
        notebook_url="x",
        endpoints=[
            # Endpoint A — src1.pdf：Amount 帶來源值 100（透過 schema.default）
            EndpointEntry(
                status="supported",
                method="POST",
                path="/a",
                summary="[NPA-F01] 付款",
                parameters=[{
                    "name": "Amount",
                    "in": "query",
                    "schema": {"type": "integer", "default": 100},
                }],
                citations=[_cite("src1.pdf")],
            ),
            # Endpoint B — src2.pdf：Amount 無值（應輸出佔位，不得繼承 A 的值）
            EndpointEntry(
                status="supported",
                method="POST",
                path="/b",
                summary="[NPA-F02] 退款",
                parameters=[{
                    "name": "Amount",
                    "in": "query",
                    "schema": {"type": "integer"},
                }],
                citations=[_cite("src2.pdf")],
            ),
        ],
    )
    openapi = build_openapi(plan)
    out = build_examples(openapi, plan)

    # Identify each endpoint's request.sh by operationId folder
    sh_a = out.get("examples/NPA_F01/request.sh")
    sh_b = out.get("examples/NPA_F02/request.sh")

    assert sh_a is not None, "examples/NPA_F01/request.sh not found"
    assert sh_b is not None, "examples/NPA_F02/request.sh not found"

    # Endpoint A must have the source value
    assert "Amount=100" in sh_a, f"Expected Amount=100 in A's request.sh:\n{sh_a}"

    # Endpoint B must have a placeholder — NOT the value from A
    assert "Amount=<amount>" in sh_b, (
        f"Expected Amount=<amount> in B's request.sh:\n{sh_b}"
    )
    assert "Amount=100" not in sh_b, (
        f"Cross-source upgrade bug: B's request.sh inherited A's value (Amount=100):\n{sh_b}"
    )
