from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from loop_apidoc.extraction.evidence import ExtractionEvidenceReference
from loop_apidoc.manifest.models import Manifest, ProcessingStatus, SourceAuthority
from loop_apidoc.plan.models import PlanItemStatus, SourceCitation

_UNUSABLE = (
    ProcessingStatus.UNREADABLE,
    ProcessingStatus.UNSUPPORTED,
    ProcessingStatus.DUPLICATE,
    ProcessingStatus.IGNORED,
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
    """Return the lone usable *document*'s identifier if the manifest collapses to
    exactly one, else None.

    Supplementary sources DO count here, and that is the point: this function
    licenses attributing an unresolvable locator to the one document present,
    and that licence rests entirely on there being only one. An excerpt of
    correspondence is a second document. Excluding it would let a citation
    reading "供應商信件 2026-08-16" be recorded as supported by the manual —
    a claim attributed to a document that never made it, which is the exact
    failure this whole authority distinction exists to prevent. With an excerpt
    in the corpus, an unresolvable locator is ambiguous and must stay
    `UNVERIFIED` until the agent cites precisely.

    `source_guard` deliberately keys off `sole_normative_source` instead, so
    adding an excerpt still does not get the whole run refused at the boundary.

    A document is a usable local source, plus each URL whose snapshot_file does
    NOT point at a usable local source. A URL saved as a local snapshot (per the
    url-fetching SOP) is the SAME document as that snapshot, so it is not counted
    twice — otherwise every SOP-following URL run would have ≥2 documents and lose
    single-source attribution. When exactly one document remains, a citation that
    names a section (not the filename), or carries no locator, is still
    attributable to it. With multiple documents we cannot disambiguate and fall
    back to strict matching. The collapsed URL returns the LOCAL file's
    relative_path (where the content actually lives, and what provenance targets),
    not the URL.
    """
    usable = [
        s.relative_path
        for s in manifest.local_sources
        if s.supported and s.status not in _UNUSABLE
    ]
    usable_set = set(usable)
    documents = list(usable)
    for url_source in manifest.url_sources:
        if url_source.snapshot_file is not None and url_source.snapshot_file in usable_set:
            continue  # 這個 URL 就是某可用本地快照檔,不另計一份文件
        documents.append(url_source.url)
    return documents[0] if len(documents) == 1 else None


def sole_normative_source(manifest: Manifest) -> str | None:
    """Return the lone usable *normative* document, ignoring supplementary ones.

    `source_guard.source_violations` skips its whole check when this is not
    None. It must ignore supplementary carriers: otherwise adding one excerpt
    to a single-manual corpus would refuse the entire run at the input
    boundary, before a run directory exists — supporting material must never
    cost the manual its run.

    This is deliberately NOT what `classify_item` uses. Skipping a boundary
    check is a decision to report problems per-entry later; attributing an
    unresolvable locator to a document is a decision to assert something about
    that document. Only the first is safe once a second document exists.
    """
    documents = [
        s.relative_path
        for s in manifest.local_sources
        if s.supported
        and s.status not in _UNUSABLE
        and s.authority is SourceAuthority.NORMATIVE
    ]
    usable_set = set(documents)
    for url_source in manifest.url_sources:
        if url_source.snapshot_file is not None and url_source.snapshot_file in usable_set:
            continue
        documents.append(url_source.url)
    return documents[0] if len(documents) == 1 else None


def classify_item(
    locator: str | None,
    *,
    query_id: str,
    answer_path: str,
    manifest: Manifest,
    evidence: Sequence[ExtractionEvidenceReference | dict] = (),
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
        evidence=tuple(evidence),
    )
    return status, citation
