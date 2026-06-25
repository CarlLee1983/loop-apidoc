from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture
def fixed_now() -> datetime:
    """Deterministic timestamp injected into time-dependent code paths."""
    return datetime(2026, 6, 25, 9, 0, 0, tzinfo=timezone.utc)
