from __future__ import annotations

import re
from pathlib import Path

from loop_apidoc.manifest.models import Manifest, ProcessingStatus
from loop_apidoc.plan.models import PlanItemStatus, SourceCitation

_UNUSABLE = (
    ProcessingStatus.UNREADABLE,
    ProcessingStatus.UNSUPPORTED,
    ProcessingStatus.DUPLICATE,
)

# A path/basename matches only when it appears bounded — not as a substring of
# a larger filename token. Leading boundary: not preceded by a filename-
# continuation char (word char, `.`, `-`). `/` is a path separator, not a token
# char, so a basename or relative path that appears as a segment of a fuller
# path (e.g. "/src/docs/api.pdf") still matches. Trailing boundary: not followed
# by a continuation char, and not by `.<word>` (an extension continuation), so a
# trailing sentence period still counts as a boundary while "api.pdf.bak" does
# not match "api.pdf". A trailing `/` stays a continuation char so a bare
# directory name does not match a deeper file path. Spaces are boundaries, so
# filenames with spaces (escaped whole) match fine.
_LEAD = r"(?<![\w.\-])"
_TRAIL = r"(?![\w/\-])(?!\.\w)"


def _bounded_match(target: str, low_locator: str) -> bool:
    pattern = _LEAD + re.escape(target.lower()) + _TRAIL
    return re.search(pattern, low_locator) is not None


def match_manifest_source(locator: str | None, manifest: Manifest) -> str | None:
    if not locator:
        return None
    low = locator.lower()
    for source in manifest.local_sources:
        rel = source.relative_path
        if _bounded_match(rel, low) or _bounded_match(Path(rel).name, low):
            return source.relative_path
    # URLs are long and specific; a full-string match keeps them safe from the
    # short-basename false positives that motivated bounded matching for paths.
    for url_source in manifest.url_sources:
        if url_source.url.lower() in low:
            return url_source.url
    return None


def sole_source(manifest: Manifest) -> str | None:
    """Return the lone usable source's identifier if the manifest has exactly one
    (a single readable/supported local file, or a single URL), else None.

    When a notebook contains exactly one source document, every grounded answer
    necessarily comes from it — NotebookLM cannot cite anything else. So an item
    whose citation names a section (not the filename), or carries no locator at
    all, is still attributable to that one source rather than left UNVERIFIED.
    With multiple sources we cannot disambiguate and fall back to strict matching.
    """
    usable = [
        s.relative_path
        for s in manifest.local_sources
        if s.supported and s.status not in _UNUSABLE
    ]
    usable += [u.url for u in manifest.url_sources]
    return usable[0] if len(usable) == 1 else None


def classify_item(
    locator: str | None,
    *,
    query_id: str,
    answer_path: str,
    manifest: Manifest,
) -> tuple[PlanItemStatus, SourceCitation]:
    manifest_source = match_manifest_source(locator, manifest)
    if manifest_source is None:
        manifest_source = sole_source(manifest)
    status = (
        PlanItemStatus.SUPPORTED
        if manifest_source
        else PlanItemStatus.UNVERIFIED
    )
    citation = SourceCitation(
        query_id=query_id,
        answer_path=answer_path,
        manifest_source=manifest_source,
        locator=locator,
    )
    return status, citation
