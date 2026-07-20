from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pymupdf
import yaml

from loop_apidoc.domain.evidence import (
    CssSelectorLocator,
    EvidenceBundle,
    EvidenceFragment,
    FragmentLocator,
    FragmentPrecision,
    JsonPointerLocator,
    LineRangeLocator,
    PageLocator,
    SectionLocator,
    SourceArtifact,
    SourceSet,
    TableCellLocator,
    TableLocator,
    UnresolvedLocator,
    WholeDocumentLocator,
    XPathLocator,
    canonical_json,
    fragment_digest,
    make_fragment_id,
    normalize_excerpt,
)
from loop_apidoc.domain.models import FrozenModel
from loop_apidoc.manifest.models import Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.source_facts.models import FactIndex, SourceFacts, TableFact


class FragmentAcquisitionError(ValueError):
    pass


class FragmentRequest(FrozenModel):
    source_id: str
    locator: FragmentLocator
    parent_fragment_id: str | None = None


_PAGE = re.compile(r"^.+?\s+(?:p\.|page\s+)(?P<page>\d+)$", re.IGNORECASE)
_LINES = re.compile(
    r"^.+?\s+lines?\s+(?P<start>\d+)-(?P<end>\d+)$",
    re.IGNORECASE,
)
_POINTER = re.compile(
    r"^.+?\.(?:json|ya?ml)#(?P<pointer>(?:/.*)?)$",
    re.IGNORECASE,
)
_PAGE_MARKER = re.compile(
    r"^\s*<!--\s*page\s*:\s*(?P<page>\d+)\s*-->\s*$",
    re.IGNORECASE,
)


def parse_legacy_locator(raw: str | None) -> FragmentLocator:
    if raw is None:
        return UnresolvedLocator(raw=None, reason="legacy locator is absent")
    value = raw.strip()
    if match := _PAGE.fullmatch(value):
        return PageLocator(page=int(match.group("page")))
    if match := _LINES.fullmatch(value):
        return LineRangeLocator(
            start_line=int(match.group("start")),
            end_line=int(match.group("end")),
        )
    if match := _POINTER.fullmatch(value):
        return JsonPointerLocator(pointer=match.group("pointer"))
    if value.startswith("css:"):
        return CssSelectorLocator(selector=value.removeprefix("css:"))
    if value.startswith("xpath:"):
        return XPathLocator(expression=value.removeprefix("xpath:"))
    if value.startswith("section:"):
        headings = tuple(
            item.strip()
            for item in value.removeprefix("section:").split(">")
            if item.strip()
        )
        if headings:
            return SectionLocator(heading_path=headings)
    return UnresolvedLocator(raw=raw, reason="legacy locator grammar is ambiguous")


def acquire_fragment_bundle(
    source_set: SourceSet,
    manifest: Manifest,
    facts: FactIndex,
    requests: tuple[FragmentRequest, ...],
    acquired_at: datetime,
) -> EvidenceBundle:
    root = Path(manifest.sources_root)
    local_by_path = {
        source.relative_path: source
        for source in manifest.local_sources
        if source.status is ProcessingStatus.PENDING
    }
    url_by_locator = {source.url: source for source in manifest.url_sources}
    facts_by_path = {source.relative_path: source for source in facts.sources}
    requests_by_source: dict[str, list[FragmentRequest]] = {}
    for request in requests:
        requests_by_source.setdefault(request.source_id, []).append(request)

    artifacts: list[SourceArtifact] = []
    fragments: dict[str, EvidenceFragment] = {}
    for descriptor in source_set.sources:
        local = local_by_path.get(descriptor.locator)
        if local is not None:
            content = (root / local.relative_path).read_bytes()
            artifact, parent = _local_parent(
                descriptor.id,
                descriptor.media_type or local.mime_type or "application/octet-stream",
                content,
                acquired_at,
                local.relative_path,
            )
            artifacts.append(artifact)
            fragments[parent.id] = parent
            source_facts = facts_by_path.get(local.relative_path)
            if source_facts is not None:
                for fragment in _fact_fragments(
                    source_facts,
                    content,
                    artifact.id,
                    parent.id,
                ):
                    fragments[fragment.id] = fragment
            for request in requests_by_source.get(descriptor.id, ()):
                fragment = _requested_fragment(
                    request,
                    local.source_format,
                    content,
                    artifact.id,
                    parent.id,
                )
                fragments[fragment.id] = fragment
            continue

        remote = url_by_locator.get(descriptor.locator)
        if remote is not None and remote.snapshot_file:
            snapshot_path = root / remote.snapshot_file
            content = snapshot_path.read_bytes()
            artifact, parent = _local_parent(
                descriptor.id,
                descriptor.media_type or "application/octet-stream",
                content,
                acquired_at,
                remote.snapshot_file,
            )
            artifacts.append(artifact)
            fragments[parent.id] = parent
            for request in requests_by_source.get(descriptor.id, ()):
                fragment = _requested_fragment(
                    request,
                    _format_from_path(remote.snapshot_file),
                    content,
                    artifact.id,
                    parent.id,
                )
                fragments[fragment.id] = fragment
            continue

        digest = (
            remote.content_sha256
            if remote is not None and remote.content_sha256
            else "unavailable"
        )
        artifact_id = _artifact_id(descriptor.id, digest)
        artifact = SourceArtifact(
            id=artifact_id,
            source_id=descriptor.id,
            media_type=descriptor.media_type or "application/octet-stream",
            content_digest=digest,
            acquired_at=acquired_at,
            acquisition_metadata=(("availability", "not_materialized"),),
        )
        parent = _document_fragment(artifact)
        artifacts.append(artifact)
        fragments[parent.id] = parent

    return EvidenceBundle(
        source_set_id=source_set.id,
        source_set_version=source_set.version,
        artifacts=tuple(sorted(artifacts, key=lambda item: item.id)),
        fragments=tuple(sorted(fragments.values(), key=lambda item: item.id)),
    )


def _local_parent(
    source_id: str,
    media_type: str,
    content: bytes,
    acquired_at: datetime,
    filename: str,
) -> tuple[SourceArtifact, EvidenceFragment]:
    digest = hashlib.sha256(content).hexdigest()
    artifact = SourceArtifact(
        id=_artifact_id(source_id, digest),
        source_id=source_id,
        media_type=media_type,
        content_digest=digest,
        acquired_at=acquired_at,
        acquisition_metadata=(("filename", filename),),
    )
    return artifact, _document_fragment(artifact)


def _artifact_id(source_id: str, digest: str) -> str:
    identity = hashlib.sha256(f"{source_id}|{digest}".encode()).hexdigest()[:24]
    return f"artifact-{identity}"


def _document_fragment(artifact: SourceArtifact) -> EvidenceFragment:
    locator = WholeDocumentLocator()
    fragment_id = make_fragment_id(
        source_artifact_id=artifact.id,
        locator=locator,
        fragment_digest=artifact.content_digest,
    )
    return EvidenceFragment(
        id=fragment_id,
        source_artifact_id=artifact.id,
        locator=locator,
        fragment_digest=artifact.content_digest,
        precision=FragmentPrecision.DOCUMENT,
    )


def _requested_fragment(
    request: FragmentRequest,
    source_format: SourceFormat,
    content: bytes,
    artifact_id: str,
    document_fragment_id: str,
) -> EvidenceFragment:
    parent_id = request.parent_fragment_id or document_fragment_id
    try:
        excerpt, semantic_value, semantic_role = _materialize_request(
            request.locator,
            source_format,
            content,
        )
    except (FragmentAcquisitionError, KeyError, IndexError, ValueError):
        return _degraded_fragment(
            request.locator,
            artifact_id,
            parent_id,
            hashlib.sha256(content).hexdigest(),
        )
    digest = fragment_digest(excerpt)
    return EvidenceFragment(
        id=make_fragment_id(
            source_artifact_id=artifact_id,
            locator=request.locator,
            fragment_digest=digest,
            parent_fragment_id=parent_id,
        ),
        source_artifact_id=artifact_id,
        locator=request.locator,
        fragment_digest=digest,
        normalized_excerpt=excerpt,
        semantic_value=semantic_value,
        semantic_role=semantic_role,
        parent_fragment_id=parent_id,
        precision=FragmentPrecision.EXACT,
    )


def _materialize_request(
    locator: FragmentLocator,
    source_format: SourceFormat,
    content: bytes,
) -> tuple[str, Any, str | None]:
    if isinstance(locator, PageLocator):
        if source_format is SourceFormat.PDF:
            document = pymupdf.open(stream=content, filetype="pdf")
            try:
                if locator.page > document.page_count:
                    raise FragmentAcquisitionError("PDF page is out of range")
                excerpt = normalize_excerpt(
                    document.load_page(locator.page - 1).get_text()
                )
            finally:
                document.close()
            return excerpt, None, None
        text = content.decode("utf-8")
        return _marked_page(text, locator.page), None, None
    if isinstance(locator, LineRangeLocator):
        lines = content.decode("utf-8").splitlines()
        if locator.end_line > len(lines):
            raise FragmentAcquisitionError("line range is out of bounds")
        excerpt = normalize_excerpt(
            "\n".join(lines[locator.start_line - 1 : locator.end_line])
        )
        return excerpt, None, None
    if isinstance(locator, JsonPointerLocator):
        text = content.decode("utf-8")
        value = (
            yaml.safe_load(text)
            if source_format is SourceFormat.OPENAPI_YAML
            else json.loads(text)
        )
        selected = _resolve_pointer(value, locator.pointer)
        return canonical_json(selected), selected, "structured.value"
    raise FragmentAcquisitionError("locator cannot be materialized safely")


def _marked_page(text: str, page: int) -> str:
    pages: dict[int, list[str]] = {}
    current: int | None = None
    for line in text.splitlines():
        if match := _PAGE_MARKER.match(line):
            current = int(match.group("page"))
            pages.setdefault(current, [])
        elif current is not None:
            pages[current].append(line)
    if page not in pages:
        raise FragmentAcquisitionError("preprocessed page marker was not found")
    return normalize_excerpt("\n".join(pages[page]))


def _resolve_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise FragmentAcquisitionError("JSON Pointer must be empty or start with '/'")
    current = value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def _degraded_fragment(
    locator: FragmentLocator,
    artifact_id: str,
    parent_id: str,
    content_digest: str,
) -> EvidenceFragment:
    return EvidenceFragment(
        id=make_fragment_id(
            source_artifact_id=artifact_id,
            locator=locator,
            fragment_digest=content_digest,
            parent_fragment_id=parent_id,
        ),
        source_artifact_id=artifact_id,
        locator=locator,
        fragment_digest=content_digest,
        parent_fragment_id=parent_id,
        precision=FragmentPrecision.UNRESOLVED,
    )


def _fact_fragments(
    facts: SourceFacts,
    content: bytes,
    artifact_id: str,
    document_fragment_id: str,
) -> tuple[EvidenceFragment, ...]:
    text = content.decode("utf-8")
    lines = text.splitlines()
    fragments: list[EvidenceFragment] = []
    for endpoint in facts.endpoints:
        if (
            endpoint.declaration_excerpt is not None
            and endpoint.declaration_start_line is not None
            and endpoint.declaration_end_line is not None
        ):
            locator = LineRangeLocator(
                start_line=endpoint.declaration_start_line,
                end_line=endpoint.declaration_end_line,
            )
            fragments.append(
                _exact_fragment(
                    artifact_id=artifact_id,
                    locator=locator,
                    excerpt=endpoint.declaration_excerpt,
                    parent_id=document_fragment_id,
                    semantic_value=f"{endpoint.method} {endpoint.path}",
                    semantic_role="endpoint.declaration",
                )
            )
        for table in endpoint.tables:
            fragments.extend(
                _table_fragments(
                    table,
                    lines,
                    artifact_id,
                    document_fragment_id,
                )
            )
    return tuple(fragments)


def _table_fragments(
    table: TableFact,
    lines: list[str],
    artifact_id: str,
    document_fragment_id: str,
) -> tuple[EvidenceFragment, ...]:
    locator = TableLocator(table_index=table.table_index)
    excerpt = normalize_excerpt(
        "\n".join(lines[table.start_line - 1 : table.end_line])
    )
    parent = _exact_fragment(
        artifact_id=artifact_id,
        locator=locator,
        excerpt=excerpt,
        parent_id=document_fragment_id,
    )
    fragments = [parent]
    for row in table.rows:
        for cell in row:
            cell_locator = TableCellLocator(
                table_index=int(cell.locator["table_index"]),
                row_index=int(cell.locator["row_index"]),
                column_index=int(cell.locator["column_index"]),
                column_name=str(cell.locator["column_name"]),
            )
            fragments.append(
                _exact_fragment(
                    artifact_id=artifact_id,
                    locator=cell_locator,
                    excerpt=cell.normalized_excerpt,
                    parent_id=parent.id,
                    semantic_value=cell.semantic_value,
                    semantic_role=f"table.{cell.locator['column_name']}",
                )
            )
    return tuple(fragments)


def _exact_fragment(
    *,
    artifact_id: str,
    locator: FragmentLocator,
    excerpt: str,
    parent_id: str,
    semantic_value: Any = None,
    semantic_role: str | None = None,
) -> EvidenceFragment:
    digest = fragment_digest(excerpt)
    return EvidenceFragment(
        id=make_fragment_id(
            source_artifact_id=artifact_id,
            locator=locator,
            fragment_digest=digest,
            parent_fragment_id=parent_id,
        ),
        source_artifact_id=artifact_id,
        locator=locator,
        fragment_digest=digest,
        normalized_excerpt=excerpt,
        semantic_value=semantic_value,
        semantic_role=semantic_role,
        parent_fragment_id=parent_id,
        precision=FragmentPrecision.EXACT,
    )


def _format_from_path(path: str) -> SourceFormat:
    lowered = path.lower()
    if lowered.endswith((".yaml", ".yml")):
        return SourceFormat.OPENAPI_YAML
    if lowered.endswith(".json"):
        return SourceFormat.OPENAPI_JSON
    if lowered.endswith(".pdf"):
        return SourceFormat.PDF
    return SourceFormat.MARKDOWN

