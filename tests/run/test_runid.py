from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.run.runid import make_run_id


def test_make_run_id_utc_format() -> None:
    now = datetime(2026, 6, 26, 10, 43, 0, tzinfo=timezone.utc)
    assert make_run_id(now) == "20260626T104300Z"
