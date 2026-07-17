import pytest
from pydantic import ValidationError

from loop_apidoc.freshness.models import (
    BatchItemResult,
    BatchItemStatus,
    BatchReport,
    FreshnessVerdict,
    Watchlist,
    WatchlistItem,
)


def test_watchlist_roundtrip_and_optional_fields():
    wl = Watchlist(items=[
        WatchlistItem(label="a", fingerprint="a/fp.json", sources="a/src", run_dir="out/a"),
        WatchlistItem(label="b", fingerprint="b/fp.json"),
    ])
    assert wl.schema_version == 1
    restored = Watchlist.model_validate_json(wl.model_dump_json())
    assert restored == wl
    assert restored.items[1].sources is None


def test_watchlist_item_forbids_extra():
    with pytest.raises(ValidationError):
        WatchlistItem.model_validate({"label": "a", "fingerprint": "f", "bogus": 1})


def test_batch_report_shape():
    r = BatchReport(
        verdict=FreshnessVerdict.CHANGED, total=2, changed_count=1,
        attention_count=0, unchanged_count=1,
        items=[BatchItemResult(label="a", status=BatchItemStatus.CHANGED, reason="version 1 -> 2")],
    )
    assert r.items[0].status is BatchItemStatus.CHANGED
    assert BatchItemStatus.ERROR.value == "error"
    assert BatchReport.model_validate_json(r.model_dump_json()) == r
