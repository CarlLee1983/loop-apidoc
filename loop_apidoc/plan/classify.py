from __future__ import annotations

import re
from pathlib import Path

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import PlanItemStatus, SourceCitation

# Split the locator into candidate tokens on whitespace and punctuation that
# never appears inside a file path. Keep `.`, `/`, `_`, `-` so paths/filenames
# stay intact ("docs/api.pdf" is one token, "v1.json" is one token).
_TOKEN = re.compile(r"[A-Za-z0-9._/\-]+")
# Punctuation that may cling to a token edge (e.g. "api.pdf." or "(api.pdf)").
_EDGE = ".,;:!?()[]{}<>\"'`§"


def _candidate_tokens(locator: str) -> set[str]:
    tokens: set[str] = set()
    for raw in _TOKEN.findall(locator.lower()):
        tokens.add(raw)
        tokens.add(raw.strip(_EDGE))
    tokens.discard("")
    return tokens


def _path_matches(rel: str, tokens: set[str]) -> bool:
    """True when relative path `rel` appears as a whole token.

    Matches the full path token or its basename token, or a longer path token
    whose final segment equals the basename — never a substring of a larger
    filename token (so "v1.json" does not match a "specv1.json" token)."""
    rel = rel.lower()
    base = Path(rel).name
    for token in tokens:
        if token == rel or token == base or token.endswith("/" + base):
            return True
    return False


def match_manifest_source(locator: str | None, manifest: Manifest) -> str | None:
    if not locator:
        return None
    low = locator.lower()
    tokens = _candidate_tokens(locator)
    for source in manifest.local_sources:
        if _path_matches(source.relative_path, tokens):
            return source.relative_path
    # URLs are long and specific; a full-string match keeps them safe from the
    # short-basename false positives that motivated token matching for paths.
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
