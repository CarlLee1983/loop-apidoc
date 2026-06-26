from __future__ import annotations

from datetime import datetime


def make_run_id(now: datetime) -> str:
    """Mint a filesystem-safe UTC run id, e.g. 20260626T104300Z."""
    return now.strftime("%Y%m%dT%H%M%SZ")
