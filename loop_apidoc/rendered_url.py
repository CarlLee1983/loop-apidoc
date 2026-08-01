"""Import browser-rendered URL evidence without contacting its origin."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from loop_apidoc.manifest.models import LocalSource, SourceFormat, UrlSource
from loop_apidoc.preparation.coverage import UrlCoverage


class RenderedUrlImportError(ValueError):
    """Rendered source provenance is invalid or would overwrite evidence."""


class CaptureMethod(str, Enum):
    BROWSER_SAVE = "browser_save"
    PLAYWRIGHT = "playwright"


class RenderedProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    original_url: str
    canonical_url: str
    captured_at: datetime
    capture_method: CaptureMethod
    imported_sha256: str
    source_file: str

    @field_validator("captured_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must include a timezone offset")
        return value


@dataclass(frozen=True)
class RenderedUrlImport:
    source_path: Path
    provenance_path: Path
    coverage_path: Path
    sha256: str


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise RenderedUrlImportError("url must be an absolute http(s) URL")
    if parts.username or parts.password:
        raise RenderedUrlImportError("url must not contain credentials")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )


def _capture_time(value: str) -> datetime:
    try:
        captured_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RenderedUrlImportError("captured_at must be an ISO-8601 timestamp") from exc
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise RenderedUrlImportError("captured_at must include a timezone offset")
    return captured_at


def _source_name(input_file: Path, filename: str | None) -> str:
    name = filename or input_file.name
    candidate = Path(name)
    if candidate.name != name or name in {".", ".."}:
        raise RenderedUrlImportError("filename must be a single file name")
    if candidate.suffix.lower() not in {".html", ".htm", ".md", ".markdown"}:
        raise RenderedUrlImportError("rendered source must be HTML or Markdown")
    return name


def import_rendered_url(
    input_file: Path,
    *,
    original_url: str,
    captured_at: str,
    capture_method: str,
    sources: Path,
    coverage_output: Path,
    filename: str | None = None,
    confirmed_by_user: bool = False,
) -> RenderedUrlImport:
    """Copy rendered bytes and write immutable provenance plus coverage."""
    canonical_url = canonicalize_url(original_url)
    captured = _capture_time(captured_at)
    try:
        method = CaptureMethod(capture_method)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in CaptureMethod)
        raise RenderedUrlImportError(
            f"capture_method must be one of: {allowed}"
        ) from exc
    name = _source_name(input_file, filename)
    source_path = sources / name
    provenance_path = source_path.with_suffix(source_path.suffix + ".source.json")
    outputs = (source_path, provenance_path, coverage_output)
    output_identities = {output.resolve(strict=False) for output in outputs}
    if len(output_identities) != len(outputs):
        raise RenderedUrlImportError("output destinations must be distinct")
    sources_identity = sources.resolve(strict=False)
    coverage_identity = coverage_output.resolve(strict=False)
    if coverage_identity.is_relative_to(
        sources_identity
    ) or sources_identity.is_relative_to(coverage_identity):
        raise RenderedUrlImportError("output destinations must not overlap")
    for output in outputs:
        if output.exists() or output.is_symlink():
            raise RenderedUrlImportError(f"output already exists: {output}")

    try:
        raw = input_file.read_bytes()
    except OSError as exc:
        raise RenderedUrlImportError(f"cannot read rendered source: {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    relative_source = name
    relative_provenance = provenance_path.name
    provenance = {
        "schema_version": 1,
        "original_url": original_url,
        "canonical_url": canonical_url,
        "captured_at": captured.isoformat(),
        "capture_method": method.value,
        "imported_sha256": digest,
        "source_file": name,
    }
    coverage = UrlCoverage(
        entry_url=canonical_url,
        confirmed_by_user=confirmed_by_user,
        expected=[{"url": canonical_url, "title": None, "source": "user"}],
        results=[
            {
                "url": canonical_url,
                "status": "fetched_rendered",
                "file": relative_source,
                "method": "playwright" if method is CaptureMethod.PLAYWRIGHT else "browser",
                "provenance_file": relative_provenance,
            }
        ],
    )

    sources.mkdir(parents=True, exist_ok=True)
    coverage_output.parent.mkdir(parents=True, exist_ok=True)
    with source_path.open("xb") as handle:
        handle.write(raw)
    with provenance_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(provenance, ensure_ascii=False, indent=2))
    with coverage_output.open("x", encoding="utf-8") as handle:
        handle.write(coverage.model_dump_json(indent=2, exclude_none=True))
    return RenderedUrlImport(
        source_path=source_path,
        provenance_path=provenance_path,
        coverage_path=coverage_output,
        sha256=digest,
    )


def _matching_local_source(
    ledger_file: str, local_sources: list[LocalSource]
) -> LocalSource:
    path = Path(ledger_file)
    if path.is_absolute() or ".." in path.parts:
        raise RenderedUrlImportError("coverage rendered file must be a safe relative path")
    matches = [
        source
        for source in local_sources
        if source.supported
        and source.source_format in {SourceFormat.HTML, SourceFormat.MARKDOWN}
        and (
            ledger_file == source.relative_path
            or ledger_file.endswith("/" + source.relative_path)
        )
    ]
    if len(matches) != 1:
        raise RenderedUrlImportError(
            "coverage rendered file must match exactly one manifest local source"
        )
    return matches[0]


def _load_provenance(
    sources_root: Path,
    provenance_file: str,
    local_source: LocalSource,
) -> RenderedProvenance:
    ledger_path = Path(provenance_file)
    if ledger_path.is_absolute() or ".." in ledger_path.parts:
        raise RenderedUrlImportError(
            "coverage provenance_file must be a safe relative path"
        )
    expected = local_source.relative_path + ".source.json"
    if not (
        provenance_file == expected or provenance_file.endswith("/" + expected)
    ):
        raise RenderedUrlImportError(
            "coverage provenance_file does not match its rendered source"
        )
    path = sources_root / expected
    try:
        return RenderedProvenance.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise RenderedUrlImportError(f"invalid rendered provenance: {path}: {exc}") from exc


def verified_rendered_url_sources(
    *,
    sources_root: Path,
    urls: list[str],
    coverage: UrlCoverage,
    local_sources: list[LocalSource],
) -> dict[str, UrlSource]:
    """Verify rendered coverage and return URL evidence keyed by canonical URL."""
    requested = {canonicalize_url(url): url for url in urls}
    verified: dict[str, UrlSource] = {}
    for result in coverage.results:
        if result.status.value != "fetched_rendered":
            continue
        key = canonicalize_url(result.url)
        if key not in requested:
            raise RenderedUrlImportError(
                f"rendered coverage URL is not present in requested URLs: {result.url}"
            )
        if key in verified:
            raise RenderedUrlImportError(
                f"rendered coverage URL is ambiguous: {result.url}"
            )
        if result.file is None or result.provenance_file is None:
            raise RenderedUrlImportError(
                "fetched_rendered coverage requires file and provenance_file"
            )
        local_source = _matching_local_source(result.file, local_sources)
        provenance = _load_provenance(
            sources_root, result.provenance_file, local_source
        )
        provenance_key = canonicalize_url(provenance.original_url)
        if provenance.canonical_url != provenance_key or provenance_key != key:
            raise RenderedUrlImportError(
                "rendered provenance URL does not match coverage/requested URL"
            )
        if provenance.schema_version != 1:
            raise RenderedUrlImportError("unsupported rendered provenance schema_version")
        if provenance.source_file != local_source.relative_path:
            raise RenderedUrlImportError(
                "rendered provenance source_file does not match the local source"
            )
        source_path = sources_root / local_source.relative_path
        try:
            digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise RenderedUrlImportError(
                f"cannot read rendered local source: {source_path}: {exc}"
            ) from exc
        if digest != provenance.imported_sha256 or digest != local_source.sha256:
            raise RenderedUrlImportError("rendered source SHA-256 does not match provenance")
        expected_method = (
            "playwright"
            if provenance.capture_method is CaptureMethod.PLAYWRIGHT
            else "browser"
        )
        if result.method is None or result.method.value != expected_method:
            raise RenderedUrlImportError(
                "rendered coverage method does not match provenance capture_method"
            )
        verified[key] = UrlSource(
            url=requested[key],
            fetched_at=provenance.captured_at,
            http_status=None,
            content_sha256=digest,
            note="fetched_rendered",
            snapshot_file=local_source.relative_path,
        )
    return verified
