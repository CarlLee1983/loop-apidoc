from __future__ import annotations

from pathlib import Path

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import PlanItemStatus, SourceCitation


def match_manifest_source(locator: str | None, manifest: Manifest) -> str | None:
    if not locator:
        return None
    low = locator.lower()
    for source in manifest.local_sources:
        rel = source.relative_path.lower()
        if rel in low or Path(source.relative_path).name.lower() in low:
            return source.relative_path
    for url_source in manifest.url_sources:
        if url_source.url.lower() in low:
            return url_source.url
    return None


def classify_item(
    locator: str | None,
    *,
    query_id: str,
    answer_path: str,
    manifest: Manifest,
) -> tuple[PlanItemStatus, SourceCitation]:
    manifest_source = match_manifest_source(locator, manifest)
    status = (
        PlanItemStatus.SUPPORTED
        if locator and manifest_source
        else PlanItemStatus.UNVERIFIED
    )
    citation = SourceCitation(
        query_id=query_id,
        answer_path=answer_path,
        manifest_source=manifest_source,
        locator=locator,
    )
    return status, citation
