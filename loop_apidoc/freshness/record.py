from __future__ import annotations

from pathlib import Path

import httpx
import yaml

from loop_apidoc.freshness.models import (
    FingerprintEntry,
    FreshnessInputError,
    SourceFingerprint,
    SourceKind,
    SourceSignal,
)
from loop_apidoc.freshness.signals import fetch_url_signal
from loop_apidoc.manifest.models import Manifest, ProcessingStatus
from loop_apidoc.preparation.coverage import CoverageInputError, ResultStatus, load_coverage

_USABLE_URL_STATUSES = {ResultStatus.FETCHED, ResultStatus.FETCHED_RENDERED}


def _read_openapi_version(run_dir: Path) -> str | None:
    path = run_dir / "openapi.yaml"
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FreshnessInputError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise FreshnessInputError(f"openapi.yaml is not valid YAML: {exc}") from exc
    info = doc.get("info") if isinstance(doc, dict) else None
    version = info.get("version") if isinstance(info, dict) else None
    return version if isinstance(version, str) else None


def _load_manifest(run_dir: Path) -> Manifest:
    path = run_dir / "manifest.json"
    try:
        return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FreshnessInputError(f"cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise FreshnessInputError(f"manifest.json is invalid JSON or fails schema: {exc}") from exc


def build_fingerprint(
    run_dir: Path,
    *,
    client: httpx.Client | None = None,
    max_bytes: int = 5 * 1024 * 1024,
) -> SourceFingerprint:
    openapi_version = _read_openapi_version(run_dir)
    manifest = _load_manifest(run_dir)

    entries: list[FingerprintEntry] = []
    for src in manifest.local_sources:
        if src.status is not ProcessingStatus.PENDING:
            continue
        entries.append(FingerprintEntry(
            id=src.relative_path,
            kind=SourceKind.LOCAL_FILE,
            signal=SourceSignal(sha256=src.sha256),
        ))

    coverage_path = run_dir / "url_sources" / "coverage.json"
    url_ids: list[str] = []
    if coverage_path.exists():
        try:
            coverage = load_coverage(coverage_path)
        except CoverageInputError as exc:
            raise FreshnessInputError(str(exc)) from exc
        seen: set[str] = set()
        for result in coverage.results:
            if result.status in _USABLE_URL_STATUSES and result.url not in seen:
                seen.add(result.url)
                url_ids.append(result.url)

    if url_ids:
        active_client = client or httpx.Client(timeout=20, follow_redirects=True, trust_env=False)
        owns_client = client is None
        try:
            for url in url_ids:
                observed = fetch_url_signal(url, client=active_client, max_bytes=max_bytes)
                if observed.failed or observed.signal is None:
                    raise FreshnessInputError(
                        f"cannot capture baseline signal for {url}: {observed.error or 'no signal'}"
                    )
                entries.append(FingerprintEntry(
                    id=url,
                    kind=observed.kind or SourceKind.WEB_URL,
                    signal=observed.signal,
                ))
        finally:
            if owns_client:
                active_client.close()

    return SourceFingerprint(
        openapi_version=openapi_version,
        recorded_from=run_dir.name,
        sources=entries,
    )


def write_fingerprint(fingerprint: SourceFingerprint, output: Path, *, force: bool = False) -> None:
    if output.exists() and not force:
        raise FreshnessInputError(f"fingerprint already exists: {output} (use --force to overwrite)")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(fingerprint.model_dump_json(indent=2), encoding="utf-8")
