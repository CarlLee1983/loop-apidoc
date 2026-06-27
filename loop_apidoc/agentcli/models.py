from __future__ import annotations

from pydantic import BaseModel


class AskResult(BaseModel):
    question: str
    notebook_url: str
    answer: str
    raw_stdout: str
    returncode: int
