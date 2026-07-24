from __future__ import annotations

from pathlib import Path

import httpx

from loop_apidoc.freshness.models import (
    FingerprintEntry,
    FreshnessReport,
    FreshnessVerdict,
    SourceFingerprint,
    SourceKind,
    SourceSignal,
    SourceResult,
    SourceObservation,
    SourceStatus,
)
from loop_apidoc.freshness.signals import ObservedSignal, classify, fetch_url_signal, hash_bytes


def _observe_local(entry: FingerprintEntry, sources_root: Path | None) -> ObservedSignal:
    if sources_root is None:
        return ObservedSignal(signal=None, failed=True, error="--sources required for local source")
    try:
        raw = (sources_root / entry.id).read_bytes()
    except OSError as exc:
        return ObservedSignal(signal=None, failed=True, error=f"cannot read local source {sources_root / entry.id}: {exc}")
    return ObservedSignal(signal=SourceSignal(sha256=hash_bytes(raw)), raw=raw, kind=SourceKind.LOCAL_FILE)


def check_freshness(
    fingerprint: SourceFingerprint,
    *,
    sources_root: Path | None = None,
    client: httpx.Client | None = None,
    max_bytes: int = 5 * 1024 * 1024,
) -> FreshnessReport:
    needs_network = any(e.kind is not SourceKind.LOCAL_FILE for e in fingerprint.sources)
    active_client = client
    owns_client = False
    if needs_network and active_client is None:
        active_client = httpx.Client(timeout=20, follow_redirects=True, trust_env=False)
        owns_client = True

    results: list[SourceResult] = []
    observations: list[SourceObservation] = []
    try:
        for entry in fingerprint.sources:
            if entry.kind is SourceKind.LOCAL_FILE:
                observed = _observe_local(entry, sources_root)
            else:
                observed = fetch_url_signal(
                    entry.id,
                    client=active_client,
                    prior_etag=entry.signal.etag,
                    prior_last_modified=entry.signal.last_modified,
                    max_bytes=max_bytes,
                )
            status, reason = classify(entry, observed)
            results.append(SourceResult(id=entry.id, kind=entry.kind, status=status, reason=reason))
            observations.append(SourceObservation(
                id=entry.id,
                kind=entry.kind,
                status=status,
                signal=observed.signal,
                raw=observed.raw,
            ))
    finally:
        if owns_client and active_client is not None:
            active_client.close()

    changed = [r for r in results if r.status is SourceStatus.CHANGED]
    inconclusive = [r for r in results if r.status is SourceStatus.FETCH_FAILED]
    unchanged_count = sum(1 for r in results if r.status is SourceStatus.UNCHANGED)
    if changed:
        verdict = FreshnessVerdict.CHANGED
    elif inconclusive:
        verdict = FreshnessVerdict.INCONCLUSIVE
    else:
        verdict = FreshnessVerdict.UNCHANGED

    return FreshnessReport(
        verdict=verdict,
        openapi_version=fingerprint.openapi_version,
        sources_total=len(results),
        unchanged_count=unchanged_count,
        changed=changed,
        inconclusive=inconclusive,
        observations=observations,
    )
