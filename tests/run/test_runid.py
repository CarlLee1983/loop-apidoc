from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.run.runid import make_run_id


def _dt(micro: int) -> datetime:
    return datetime(2026, 6, 26, 10, 43, 0, micro, tzinfo=timezone.utc)


def test_make_run_id_utc_format() -> None:
    assert make_run_id(_dt(0)) == "20260626T104300.000000Z"


def test_distinct_close_timestamps_produce_distinct_ids() -> None:
    """同一秒、僅相差微秒的兩個時間,必須產出不同的 run id。"""
    assert make_run_id(_dt(1)) != make_run_id(_dt(2))


def test_run_id_is_filesystem_safe_and_sortable() -> None:
    rid = make_run_id(_dt(123456))
    for bad in "/\\:*?\"<>| ":
        assert bad not in rid
    assert rid.endswith("Z")
    assert make_run_id(_dt(1)) < make_run_id(_dt(2))
