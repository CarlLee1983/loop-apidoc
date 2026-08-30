"""Download one machine-readable OpenAPI document as immutable source evidence."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .url_safety import UrlSafetyError, safe_client
import yaml

from loop_apidoc.url_coverage import UrlCoverage


class OpenApiSnapshotError(ValueError):
    """A direct URL could not become a safe, valid local OpenAPI snapshot."""


@dataclass(frozen=True)
class OpenApiSnapshot:
    snapshot_path: Path
    coverage_path: Path
    sha256: str


StageFile = Callable[[Path, bytes], Path]


def _stage_file(target: Path, content: bytes) -> Path:
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        staged = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return staged


def _publish_no_clobber(staged: Path, target: Path) -> None:
    try:
        os.link(staged, target)
    except FileExistsError as exc:
        raise OpenApiSnapshotError(
            f"snapshot output already exists: {target}"
        ) from exc


def _rollback_if_owned(staged: Path, target: Path) -> None:
    try:
        staged_metadata = staged.stat()
        target_metadata = target.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (staged_metadata.st_dev, staged_metadata.st_ino) == (
        target_metadata.st_dev,
        target_metadata.st_ino,
    ):
        target.unlink()


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
    stage_file: StageFile | None = None,
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

    active_client = client or safe_client()
    owns_client = client is None
    try:
        response = active_client.get(
            url,
            headers={"accept": "application/json, application/yaml, text/yaml"},
        )
        response.raise_for_status()
    except UrlSafetyError as exc:
        # Surface as this module's own error so the CLI handler catches it and
        # exits 2 with a message, rather than printing a traceback.
        raise OpenApiSnapshotError(f"refused by egress policy: {exc}") from exc
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
    snapshot_identity = snapshot_path.resolve(strict=False)
    coverage_identity = coverage_output.resolve(strict=False)
    if snapshot_identity == coverage_identity:
        raise OpenApiSnapshotError(
            "snapshot and coverage destinations must be distinct"
        )
    sources_identity = sources.resolve(strict=False)
    if coverage_identity.is_relative_to(
        sources_identity
    ) or sources_identity.is_relative_to(coverage_identity):
        raise OpenApiSnapshotError(
            "snapshot and coverage destinations must not overlap"
        )
    if snapshot_path.exists() or snapshot_path.is_symlink():
        raise OpenApiSnapshotError(f"snapshot already exists: {snapshot_path}")
    if coverage_output.exists() or coverage_output.is_symlink():
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
    coverage_bytes = ledger.model_dump_json(
        indent=2,
        exclude_none=True,
    ).encode("utf-8")
    stage = stage_file or _stage_file
    snapshot_temp: Path | None = None
    coverage_temp: Path | None = None
    snapshot_published = False
    try:
        snapshot_temp = stage(snapshot_path, raw)
        coverage_temp = stage(coverage_output, coverage_bytes)
        _publish_no_clobber(snapshot_temp, snapshot_path)
        snapshot_published = True
        _publish_no_clobber(coverage_temp, coverage_output)
    except (OpenApiSnapshotError, OSError):
        if snapshot_published and snapshot_temp is not None:
            _rollback_if_owned(snapshot_temp, snapshot_path)
        raise
    finally:
        if snapshot_temp is not None:
            snapshot_temp.unlink(missing_ok=True)
        if coverage_temp is not None:
            coverage_temp.unlink(missing_ok=True)
    return OpenApiSnapshot(
        snapshot_path=snapshot_path,
        coverage_path=coverage_output,
        sha256=hashlib.sha256(raw).hexdigest(),
    )
