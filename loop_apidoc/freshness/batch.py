from __future__ import annotations

import json
from pathlib import Path

import httpx
from pydantic import ValidationError

from loop_apidoc.freshness.check import check_freshness
from loop_apidoc.freshness.models import (
    BatchItemResult,
    BatchItemStatus,
    BatchReport,
    FreshnessInputError,
    FreshnessReport,
    FreshnessVerdict,
    SourceFingerprint,
    Watchlist,
    WatchlistItem,
)

_VERDICT_TO_STATUS = {
    FreshnessVerdict.UNCHANGED: BatchItemStatus.UNCHANGED,
    FreshnessVerdict.CHANGED: BatchItemStatus.CHANGED,
    FreshnessVerdict.INCONCLUSIVE: BatchItemStatus.INCONCLUSIVE,
}


def load_watchlist(path: Path) -> Watchlist:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FreshnessInputError(f"cannot read watchlist {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FreshnessInputError(f"watchlist is not valid JSON: {exc}") from exc
    try:
        return Watchlist.model_validate(data)
    except ValidationError as exc:
        raise FreshnessInputError(f"watchlist schema error: {exc}") from exc


def _summarize(report: FreshnessReport) -> str | None:
    flagged = report.changed + report.inconclusive
    if not flagged:
        return None
    return "; ".join(f"{r.id}: {r.reason}" for r in flagged if r.reason) or None


def _scan_item(item: WatchlistItem, base_dir: Path, client: httpx.Client, max_bytes: int) -> BatchItemResult:
    try:
        fp_path = base_dir / item.fingerprint
        fingerprint = SourceFingerprint.model_validate_json(fp_path.read_text(encoding="utf-8"))
        sources_root = (base_dir / item.sources) if item.sources else None
        report = check_freshness(fingerprint, sources_root=sources_root, client=client, max_bytes=max_bytes)
    except (FreshnessInputError, OSError, ValueError) as exc:
        return BatchItemResult(label=item.label, status=BatchItemStatus.ERROR, reason=str(exc), run_dir=item.run_dir)
    return BatchItemResult(
        label=item.label,
        status=_VERDICT_TO_STATUS[report.verdict],
        openapi_version=report.openapi_version,
        reason=_summarize(report),
        run_dir=item.run_dir,
    )


def scan_watchlist(
    watchlist: Watchlist,
    *,
    base_dir: Path,
    client: httpx.Client | None = None,
    max_bytes: int = 5 * 1024 * 1024,
) -> BatchReport:
    active_client = client
    owns_client = False
    if active_client is None and watchlist.items:
        active_client = httpx.Client(timeout=20, follow_redirects=True, trust_env=False)
        owns_client = True

    results: list[BatchItemResult] = []
    try:
        for item in watchlist.items:
            results.append(_scan_item(item, base_dir, active_client, max_bytes))
    finally:
        if owns_client and active_client is not None:
            active_client.close()

    changed = sum(1 for r in results if r.status is BatchItemStatus.CHANGED)
    unchanged = sum(1 for r in results if r.status is BatchItemStatus.UNCHANGED)
    attention = sum(1 for r in results if r.status in (BatchItemStatus.INCONCLUSIVE, BatchItemStatus.ERROR))
    if changed:
        verdict = FreshnessVerdict.CHANGED
    elif attention:
        verdict = FreshnessVerdict.INCONCLUSIVE
    else:
        verdict = FreshnessVerdict.UNCHANGED

    return BatchReport(
        verdict=verdict,
        total=len(results),
        changed_count=changed,
        attention_count=attention,
        unchanged_count=unchanged,
        items=results,
    )
