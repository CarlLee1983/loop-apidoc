from __future__ import annotations

from typing import Callable, TypeVar

from loop_apidoc.notebooklm.errors import TransientError

T = TypeVar("T")


def run_with_retries(operation: Callable[[], T], *, max_attempts: int = 3) -> T:
    """Run operation, retrying ONLY on TransientError up to max_attempts total
    attempts. Non-transient errors propagate immediately (stop). These technical
    retries are counted separately from the three correction rounds (spec §11)."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    last_error: TransientError | None = None
    for _ in range(max_attempts):
        try:
            return operation()
        except TransientError as error:
            last_error = error
    assert last_error is not None
    raise last_error
