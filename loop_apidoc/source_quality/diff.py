from __future__ import annotations

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.source_quality.models import SourceDiffEntry, SourceDiffReport


def build_source_diff(*, base: Manifest, head: Manifest) -> SourceDiffReport:
    base_sources = {source.relative_path: source for source in base.local_sources}
    head_sources = {source.relative_path: source for source in head.local_sources}
    entries: list[SourceDiffEntry] = []
    for path in sorted(base_sources.keys() - head_sources.keys()):
        entries.append(SourceDiffEntry(path=path, kind="removed", summary="Source file removed."))
    for path in sorted(head_sources.keys() - base_sources.keys()):
        entries.append(SourceDiffEntry(path=path, kind="added", summary="Source file added."))
    for path in sorted(base_sources.keys() & head_sources.keys()):
        before, after = base_sources[path], head_sources[path]
        if (before.sha256, before.status, before.supported) != (after.sha256, after.status, after.supported):
            entries.append(SourceDiffEntry(path=path, kind="changed", summary="Source file hash or availability changed."))
    return SourceDiffReport(entries=entries)
