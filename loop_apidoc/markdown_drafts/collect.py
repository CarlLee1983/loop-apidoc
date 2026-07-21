"""Read manifest-named Markdown sources into non-authoritative draft facts."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from loop_apidoc.manifest.models import Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.markdown_drafts.markdown import scan_markdown_drafts
from loop_apidoc.markdown_drafts.models import MarkdownDraftIndex


class MarkdownDraftInputError(ValueError):
    """Raised when a manifest cannot be used as a draft collection boundary."""


def load_manifest(path: Path) -> Manifest:
    """Load a manifest with a concise, command-safe error."""
    try:
        return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise MarkdownDraftInputError(f"cannot load manifest {path}: {exc}") from exc


def collect_markdown_drafts(sources_root: Path, manifest: Manifest) -> MarkdownDraftIndex:
    """Scan only usable Markdown files explicitly named by the manifest."""
    drafts = []
    for entry in manifest.local_sources:
        if entry.source_format is not SourceFormat.MARKDOWN:
            continue
        if entry.status is not ProcessingStatus.PENDING:
            continue
        try:
            text = (sources_root / entry.relative_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        drafts.append(scan_markdown_drafts(entry.relative_path, text))
    return MarkdownDraftIndex(sources=tuple(drafts))
