from __future__ import annotations

from pydantic import BaseModel


class AuthStatus(BaseModel):
    authenticated: bool
    raw_stdout: str
    stale_warning: str | None = None


class AskResult(BaseModel):
    question: str
    notebook_url: str
    answer: str
    raw_stdout: str
    returncode: int
