from __future__ import annotations

from loop_apidoc.extraction.stages import (
    STAGES,
    QueryKind,
    QueryStage,
    StageMode,
    stage_by_id,
)


def test_ten_stages_in_order():
    assert len(STAGES) == 10
    assert [s.stage_id for s in STAGES] == [f"{i:02d}" for i in range(1, 11)]


def test_structured_stages_have_json_contract():
    structured = {"03", "04", "05", "06", "07", "08", "09"}
    for stage in STAGES:
        if stage.stage_id in structured:
            assert stage.mode is StageMode.STRUCTURED
            assert stage.json_key
            assert stage.json_hint and "missing" in stage.json_hint
        else:
            assert stage.mode is StageMode.NARRATIVE
            assert stage.json_key is None


def test_endpoint_stage_key():
    assert stage_by_id("05").json_key == "endpoints"
    assert stage_by_id("05").mode is StageMode.STRUCTURED


def test_query_kinds():
    assert QueryKind.INITIAL.value == "initial"
    assert QueryKind.FOLLOWUP.value == "followup"
    assert QueryKind.REVERSE.value == "reverse"


def test_stage_by_id_unknown_raises():
    import pytest

    with pytest.raises(KeyError):
        stage_by_id("99")


def test_stage_is_a_model():
    assert isinstance(STAGES[0], QueryStage)
