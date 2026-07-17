from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

from loop_apidoc.freshness.models import (
    FingerprintEntry,
    FreshnessInputError,
    SourceKind,
    SourceSignal,
    SourceStatus,
)


def hash_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_signal(path: Path) -> SourceSignal:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FreshnessInputError(f"cannot read local source {path}: {exc}") from exc
    return SourceSignal(sha256=hash_bytes(raw))


def detect_openapi(raw: bytes, content_type: str) -> tuple[bool, str | None]:
    """Return (is_openapi_document, info.version). Never raises."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return (False, None)
    is_yaml = "yaml" in content_type.lower()
    try:
        parsed = yaml.safe_load(text) if is_yaml else json.loads(text)
    except (json.JSONDecodeError, yaml.YAMLError):
        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError:
            return (False, None)
    if not isinstance(parsed, dict):
        return (False, None)
    version_field = parsed.get("openapi")
    is_openapi = parsed.get("swagger") == "2.0" or (
        isinstance(version_field, str) and version_field.startswith("3.")
    )
    if not is_openapi:
        return (False, None)
    info = parsed.get("info")
    info_version = info.get("version") if isinstance(info, dict) else None
    return (True, info_version if isinstance(info_version, str) else None)


@dataclass(frozen=True)
class ObservedSignal:
    signal: SourceSignal | None
    not_modified: bool = False
    failed: bool = False
    error: str | None = None
    kind: SourceKind | None = None


def classify(entry: FingerprintEntry, observed: ObservedSignal) -> tuple[SourceStatus, str | None]:
    if observed.failed:
        return (SourceStatus.FETCH_FAILED, observed.error or "fetch failed")
    if observed.not_modified:
        return (SourceStatus.UNCHANGED, None)
    current = observed.signal
    if current is None:  # defensive: no signal and not a failure/304 → cannot judge
        return (SourceStatus.FETCH_FAILED, "no signal produced")

    baseline = entry.signal
    if entry.kind is SourceKind.OPENAPI_URL and baseline.version and current.version:
        if baseline.version == current.version:
            return (SourceStatus.UNCHANGED, None)
        return (SourceStatus.CHANGED, f"version {baseline.version} -> {current.version}")

    if baseline.sha256 == current.sha256:
        return (SourceStatus.UNCHANGED, None)
    return (SourceStatus.CHANGED, "content hash changed")


def fetch_url_signal(
    url: str,
    *,
    client: httpx.Client,
    prior_etag: str | None = None,
    prior_last_modified: str | None = None,
    max_bytes: int = 5 * 1024 * 1024,
) -> ObservedSignal:
    headers: dict[str, str] = {"accept": "application/json, application/yaml, text/yaml, text/html"}
    if prior_etag:
        headers["if-none-match"] = prior_etag
    if prior_last_modified:
        headers["if-modified-since"] = prior_last_modified
    try:
        response = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return ObservedSignal(signal=None, failed=True, error=f"fetch failed: {exc}")
    if response.status_code == 304:
        return ObservedSignal(signal=None, not_modified=True)
    if response.status_code >= 400:
        return ObservedSignal(signal=None, failed=True, error=f"HTTP {response.status_code}")
    raw = response.content
    if len(raw) > max_bytes:
        return ObservedSignal(signal=None, failed=True, error=f"response exceeded {max_bytes} byte cap")
    content_type = response.headers.get("content-type", "")
    is_openapi, version = detect_openapi(raw, content_type)
    signal = SourceSignal(
        version=version,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
        sha256=hash_bytes(raw),
    )
    kind = SourceKind.OPENAPI_URL if is_openapi else SourceKind.WEB_URL
    return ObservedSignal(signal=signal, kind=kind)
