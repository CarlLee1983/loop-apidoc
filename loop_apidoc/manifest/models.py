from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceFormat(str, Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    WORD = "word"
    OPENAPI_JSON = "openapi-json"
    OPENAPI_YAML = "openapi-yaml"
    HTML = "html"
    UNKNOWN = "unknown"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    UNSUPPORTED = "unsupported"
    DUPLICATE = "duplicate"
    UNREADABLE = "unreadable"
    # Matched an exclude glob: present in the manifest for visibility, but never
    # treated as source evidence.
    IGNORED = "ignored"


class LocalSource(BaseModel):
    relative_path: str
    mime_type: str | None
    source_format: SourceFormat
    size_bytes: int
    sha256: str
    scanned_at: datetime
    supported: bool
    status: ProcessingStatus
    duplicate_of: str | None = None


class UrlSource(BaseModel):
    url: str
    fetched_at: datetime
    http_status: int | None
    content_sha256: str | None = None
    note: str | None = None
    snapshot_file: str | None = None


class Manifest(BaseModel):
    sources_root: str
    generated_at: datetime
    local_sources: list[LocalSource] = Field(default_factory=list)
    url_sources: list[UrlSource] = Field(default_factory=list)

    def unsupported(self) -> list[LocalSource]:
        return [s for s in self.local_sources if s.status is ProcessingStatus.UNSUPPORTED]

    def duplicates(self) -> list[LocalSource]:
        return [s for s in self.local_sources if s.status is ProcessingStatus.DUPLICATE]

    def unreadable(self) -> list[LocalSource]:
        return [s for s in self.local_sources if s.status is ProcessingStatus.UNREADABLE]
