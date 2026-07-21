"""Read manifest-scoped Markdown inputs for the extraction scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loop_apidoc.manifest.models import Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.markdown_drafts.markdown import scan_markdown_drafts
from loop_apidoc.markdown_drafts.models import MarkdownDraftIndex


class ExtractionScaffoldInputError(ValueError):
    """Raised when a scaffold cannot be collected or written safely."""


@dataclass(frozen=True)
class ScaffoldInputs:
    """The readable Markdown evidence passed into pure projection."""

    drafts: MarkdownDraftIndex
    source_texts: dict[str, str]


def collect_scaffold_inputs(sources_root: Path, manifest: Manifest) -> ScaffoldInputs:
    """Read only readable, pending Markdown entries named by the manifest."""
    if not sources_root.is_dir():
        raise ExtractionScaffoldInputError(f"sources root is not a directory: {sources_root}")
    source_texts: dict[str, str] = {}
    drafts = []
    for entry in manifest.local_sources:
        if entry.source_format is not SourceFormat.MARKDOWN or entry.status is not ProcessingStatus.PENDING:
            continue
        try:
            text = (sources_root / entry.relative_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        source_texts[entry.relative_path] = text
        drafts.append(scan_markdown_drafts(entry.relative_path, text))
    if not drafts:
        raise ExtractionScaffoldInputError("no usable Markdown sources named by manifest")
    return ScaffoldInputs(drafts=MarkdownDraftIndex(sources=tuple(drafts)), source_texts=source_texts)
