from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FreshnessInputError(Exception):
    """Raised when fingerprint/run-dir input is unreadable or malformed."""


class SourceKind(str, Enum):
    OPENAPI_URL = "openapi_url"
    WEB_URL = "web_url"
    LOCAL_FILE = "local_file"


class SourceStatus(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    FETCH_FAILED = "fetch_failed"


class FreshnessVerdict(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    INCONCLUSIVE = "inconclusive"


class SourceSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    sha256: str | None = None


class FingerprintEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: SourceKind
    signal: SourceSignal


class SourceFingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    openapi_version: str | None = None
    recorded_from: str | None = None
    sources: list[FingerprintEntry] = Field(default_factory=list)


class SourceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: SourceKind
    status: SourceStatus
    reason: str | None = None


class SourceObservation(BaseModel):
    """The bytes and signal observed during one freshness classification.

    Raw bytes are deliberately excluded from serialized freshness reports.  They
    exist only long enough for governance to retain a changed source without a
    second, racy fetch.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: SourceKind
    status: SourceStatus
    signal: SourceSignal | None = None
    raw: bytes | None = Field(default=None, exclude=True)


class FreshnessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: FreshnessVerdict
    openapi_version: str | None = None
    sources_total: int
    unchanged_count: int
    changed: list[SourceResult] = Field(default_factory=list)
    inconclusive: list[SourceResult] = Field(default_factory=list)
    observations: list[SourceObservation] = Field(default_factory=list, exclude=True)


EXIT_CODES: dict[FreshnessVerdict, int] = {
    FreshnessVerdict.UNCHANGED: 0,
    FreshnessVerdict.CHANGED: 1,
    FreshnessVerdict.INCONCLUSIVE: 2,
}


class WatchlistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    fingerprint: str
    sources: str | None = None
    run_dir: str | None = None


class Watchlist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    items: list[WatchlistItem] = Field(default_factory=list)


class BatchItemStatus(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"


class BatchItemResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    status: BatchItemStatus
    openapi_version: str | None = None
    reason: str | None = None
    run_dir: str | None = None
    observations: list[SourceObservation] = Field(default_factory=list, exclude=True)


class BatchReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: FreshnessVerdict
    total: int
    changed_count: int
    attention_count: int
    unchanged_count: int
    items: list[BatchItemResult] = Field(default_factory=list)
