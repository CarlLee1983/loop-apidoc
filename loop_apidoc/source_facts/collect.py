"""本套件唯一的讀檔出口:把 manifest 指名的 Markdown 來源掃成事實索引。

讀不動的來源在這裡靜默略過——manifest coverage 已經把 UNREADABLE 當成
驗證錯誤回報,這裡再擋一次只會把同一件事講兩遍,還會讓整個閘門因為
一個壞檔而失能。
"""

from __future__ import annotations

from pathlib import Path

from loop_apidoc.manifest.models import Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.source_facts.markdown import scan_markdown
from loop_apidoc.source_facts.models import FactIndex


def collect_facts(sources_root: Path, manifest: Manifest) -> FactIndex:
    """掃描 manifest 中可用的 Markdown 來源,回傳機械事實索引。"""
    sources = []
    for entry in manifest.local_sources:
        if entry.source_format is not SourceFormat.MARKDOWN:
            continue
        if entry.status is not ProcessingStatus.PENDING:
            continue
        text = _read(sources_root / entry.relative_path)
        if text is None:
            continue
        sources.append(scan_markdown(entry.relative_path, text))
    return FactIndex(sources=sources)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
