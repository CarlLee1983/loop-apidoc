from __future__ import annotations

import pytest

from loop_apidoc.notebooklm.errors import AuthRequired, TransientError
from loop_apidoc.notebooklm.retry import run_with_retries


def test_succeeds_after_transient_then_success():
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        if calls["n"] < 2:
            raise TransientError("temporary")
        return "ok"

    assert run_with_retries(operation, max_attempts=3) == "ok"
    assert calls["n"] == 2


def test_non_transient_propagates_immediately_without_retry():
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        raise AuthRequired("stop")

    with pytest.raises(AuthRequired):
        run_with_retries(operation, max_attempts=3)
    assert calls["n"] == 1  # not retried


def test_exhausts_attempts_then_reraises_last_transient():
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        raise TransientError(f"fail {calls['n']}")

    with pytest.raises(TransientError):
        run_with_retries(operation, max_attempts=3)
    assert calls["n"] == 3


def test_invalid_max_attempts_raises():
    with pytest.raises(ValueError):
        run_with_retries(lambda: "x", max_attempts=0)
