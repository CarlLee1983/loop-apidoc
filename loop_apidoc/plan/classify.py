from __future__ import annotations

import re
from pathlib import Path

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import PlanItemStatus, SourceCitation

# A path/basename matches only when it appears bounded — not as a substring of
# a larger filename token. Leading boundary: not preceded by a filename-
# continuation char (word char, `.`, `/`, `-`). Trailing boundary: not followed
# by a continuation char, and not by `.<word>` (an extension continuation), so a
# trailing sentence period still counts as a boundary while "api.pdf.bak" does
# not match "api.pdf". Spaces are boundaries, so filenames with spaces (escaped
# whole) match fine — fixing the regression of pure whitespace tokenization.
_LEAD = r"(?<![\w./\-])"
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
