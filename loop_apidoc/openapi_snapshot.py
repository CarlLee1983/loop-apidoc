"""Download one machine-readable OpenAPI document as immutable source evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

from loop_apidoc.preparation.coverage import UrlCoverage


class OpenApiSnapshotError(ValueError):
    """A direct URL could not become a safe, valid local OpenAPI snapshot."""


@dataclass(frozen=True)
class OpenApiSnapshot:
    snapshot_path: Path
    coverage_path: Path
    sha256: str


def _snapshot_name(url: str, content_type: str, filename: str | None) -> str:
    if filename:
        candidate = Path(filename)
        if candidate.name != filename or filename in {".", ".."}:
            raise OpenApiSnapshotError("filename must be a single file name")
        return filename
    path_name = Path(urlparse(url).path).name
    if path_name.lower().endswith((".json", ".yaml", ".yml")):
        return path_name
    return "openapi.yaml" if "yaml" in content_type.lower() else "openapi.json"


def _parse_openapi(raw: bytes, content_type: str, name: str) -> dict:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OpenApiSnapshotError("response is not UTF-8 JSON/YAML") from exc
    is_yaml = name.lower().endswith((".yaml", ".yml")) or "yaml" in content_type.lower()
    try:
        parsed = yaml.safe_load(text) if is_yaml else json.loads(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise OpenApiSnapshotError("response is not valid OpenAPI JSON/YAML") from exc
    if not isinstance(parsed, dict):
        raise OpenApiSnapshotError("OpenAPI document root must be an object")
    version = parsed.get("openapi")
    if not (parsed.get("swagger") == "2.0" or isinstance(version, str) and version.startswith("3.")):
        raise OpenApiSnapshotError("response does not declare Swagger 2.0 or OpenAPI 3.x")
    return parsed


def snapshot_openapi_url(
    url: str,
    *,
    sources: Path,
    coverage_output: Path,
    filename: str | None = None,
    confirmed_by_user: bool = False,
    max_bytes: int = 5 * 1024 * 1024,
    client: httpx.Client | None = None,
) -> OpenApiSnapshot:
    """Fetch one OpenAPI JSON/YAML URL and write source evidence plus coverage.

    Neither the source snapshot nor coverage ledger is overwritten. This makes a
    rerun with the same output paths fail loudly instead of mutating evidence.
    """
    parsed_url = urlparse(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise OpenApiSnapshotError("url must be an absolute http(s) URL")
    if max_bytes < 1:
        raise OpenApiSnapshotError("max_bytes must be positive")

    active_client = client or httpx.Client(timeout=20, follow_redirects=True, trust_env=False)
    owns_client = client is None
    try:
        response = active_client.get(
            url,
            headers={"accept": "application/json, application/yaml, text/yaml"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OpenApiSnapshotError(f"fetch failed: {exc}") from exc
    finally:
        if owns_client:
            active_client.close()

    raw = response.content
    if len(raw) > max_bytes:
        raise OpenApiSnapshotError(f"response exceeded {max_bytes} byte cap")
    content_type = response.headers.get("content-type", "")
    name = _snapshot_name(str(response.url), content_type, filename)
    document = _parse_openapi(raw, content_type, name)
    snapshot_path = sources / name
    if snapshot_path.exists():
        raise OpenApiSnapshotError(f"snapshot already exists: {snapshot_path}")
    if coverage_output.exists():
        raise OpenApiSnapshotError(f"coverage file already exists: {coverage_output}")

    title = document.get("info", {}).get("title") if isinstance(document.get("info"), dict) else None
    ledger = UrlCoverage(
        entry_url=url,
        confirmed_by_user=confirmed_by_user,
        expected=[{"url": url, "title": title, "source": "user"}],
        results=[{
            "url": url,
            "status": "fetched",
            "file": f"sources/{name}",
            "method": "direct",
        }],
    )
    sources.mkdir(parents=True, exist_ok=True)
    coverage_output.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_bytes(raw)
    coverage_output.write_text(ledger.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
    return OpenApiSnapshot(
        snapshot_path=snapshot_path,
        coverage_path=coverage_output,
        sha256=hashlib.sha256(raw).hexdigest(),
    )
