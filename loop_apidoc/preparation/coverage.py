"""Compatibility re-export for the former preparation-owned coverage ledger."""

from loop_apidoc.url_coverage import (
    CoverageExpected,
    CoverageInputError,
    CoverageResult,
    ExpectedSource,
    FetchMethod,
    ResultStatus,
    UrlCoverage,
    load_coverage,
    normalize_url,
)

__all__ = [
    "CoverageExpected",
    "CoverageInputError",
    "CoverageResult",
    "ExpectedSource",
    "FetchMethod",
    "ResultStatus",
    "UrlCoverage",
    "load_coverage",
    "normalize_url",
]
