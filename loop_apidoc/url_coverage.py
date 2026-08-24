"""Load and validate the agent-written URL acquisition coverage ledger.

The ledger records acquisition evidence shared by source fetchers, manifest
assembly, readiness assessment, and freshness reporting.  It is deliberately
outside any one of those adapters so its schema and parser have one owner.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError


class CoverageInputError(Exception):
    """Raised when url_sources/coverage.json is unreadable or malformed."""


class ExpectedSource(str, Enum):
    NAV = "nav"
    SITEMAP = "sitemap"
    USER = "user"


class ResultStatus(str, Enum):
    FETCHED = "fetched"
    FETCHED_RENDERED = "fetched_rendered"
    EMPTY_SUSPECT = "empty_suspect"
    FETCH_FAILED = "fetch_failed"
    AUTH_REQUIRED = "auth_required"
    SKIPPED_BY_USER = "skipped_by_user"


class FetchMethod(str, Enum):
    DEFUDDLE = "defuddle"
    PLAYWRIGHT = "playwright"
    BROWSER = "browser"
    DIRECT = "direct"


class CoverageExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str | None = None
    source: ExpectedSource


class CoverageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    status: ResultStatus
    file: str | None = None
    method: FetchMethod | None = None
    provenance_file: str | None = None
    note: str | None = None


class UrlCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_url: str
    confirmed_by_user: bool = False
    expected: list[CoverageExpected] = []
    results: list[CoverageResult] = []


def normalize_url(url: str) -> str:
    """Normalize a URL for coverage matching without treating fragments as pages."""
    return url.split("#", 1)[0].rstrip("/")


def load_coverage(path: Path) -> UrlCoverage:
    """Read and validate coverage.json without accepting malformed ledgers."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CoverageInputError(f"cannot read coverage file {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CoverageInputError(f"coverage.json is not valid JSON: {exc}") from exc
    try:
        return UrlCoverage.model_validate(data)
    except ValidationError as exc:
        raise CoverageInputError(
            f"coverage.json schema error: {_first_error(exc)}"
        ) from exc


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(part) for part in err["loc"]) or "(root)"
    return f"{loc}: {err['msg']}"
