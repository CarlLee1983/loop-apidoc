from __future__ import annotations

from datetime import datetime


def make_run_id(now: datetime) -> str:
    """Mint a filesystem-safe UTC run id with subsecond precision, e.g.
    20260626T104300.123456Z. Subsecond precision keeps two runs started in the
    same second from colliding on the same run directory."""
    return now.strftime("%Y%m%dT%H%M%S.%fZ")
