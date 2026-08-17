from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
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
from loop_apidoc.manifest.formats import detect_format
from loop_apidoc.manifest.models import Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.source_facts.models import FactIndex, SourceFacts, TableFact


class FragmentAcquisitionError(ValueError):
    pass


class FragmentRequest(FrozenModel):
    source_id: str
    locator: FragmentLocator
    parent_fragment_id: str | None = None


_UNPREPARED = object()


@dataclass(frozen=True)
class _PreparedSource:
    content_digest: str
    lines: tuple[str, ...] | None
    marked_pages: dict[int, str] | None
    pdf_pages: dict[int, str] | None
    structured: Any
    text_error: ValueError | None
    structured_error: ValueError | None

    def materialize(
        self,
        locator: FragmentLocator,
    ) -> tuple[str, Any, str | None]:
        if self.text_error is not None and isinstance(
            locator,
            (PageLocator, LineRangeLocator, JsonPointerLocator),
        ):
            raise self.text_error
        if isinstance(locator, PageLocator):
            pages = self.pdf_pages if self.pdf_pages is not None else self.marked_pages
            if pages is None or locator.page not in pages:
                raise FragmentAcquisitionError("requested page was not found")
            return pages[locator.page], None, None
        if isinstance(locator, LineRangeLocator):
            if self.lines is None or locator.end_line > len(self.lines):
                raise FragmentAcquisitionError("line range is out of bounds")
            excerpt = normalize_excerpt(
                "\n".join(self.lines[locator.start_line - 1 : locator.end_line])
            )
            return excerpt, None, None
        if isinstance(locator, JsonPointerLocator):
            if self.structured_error is not None:
                raise self.structured_error
            if self.structured is _UNPREPARED:
                raise FragmentAcquisitionError("structured source was not prepared")
            selected = _resolve_pointer(self.structured, locator.pointer)
            return canonical_json(selected), selected, "structured.value"
        raise FragmentAcquisitionError("locator cannot be materialized safely")


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
            for fragment in _requested_fragments(
                requests_by_source.get(descriptor.id, ()),
                local.source_format,
                content,
                artifact.id,
                parent.id,
            ):
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
            for fragment in _requested_fragments(
                requests_by_source.get(descriptor.id, ()),
                _format_from_path(remote.snapshot_file),
                content,
                artifact.id,
                parent.id,
            ):
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


def _requested_fragments(
    requests: Sequence[FragmentRequest],
    source_format: SourceFormat,
    content: bytes,
    artifact_id: str,
    document_fragment_id: str,
) -> tuple[EvidenceFragment, ...]:
    if not requests:
        return ()
    prepared = _prepare_source(source_format, content, requests)
    return tuple(
        _requested_fragment(
            request,
            prepared,
            artifact_id,
            document_fragment_id,
        )
        for request in requests
    )


def _requested_fragment(
    request: FragmentRequest,
    prepared: _PreparedSource,
    artifact_id: str,
    document_fragment_id: str,
) -> EvidenceFragment:
    parent_id = request.parent_fragment_id or document_fragment_id
    try:
        excerpt, semantic_value, semantic_role = prepared.materialize(request.locator)
    except (FragmentAcquisitionError, KeyError, IndexError, ValueError):
        return _degraded_fragment(
            request.locator,
            artifact_id,
            parent_id,
            prepared.content_digest,
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


def _prepare_source(
    source_format: SourceFormat,
    content: bytes,
    requests: Sequence[FragmentRequest],
) -> _PreparedSource:
    locators = tuple(request.locator for request in requests)
    needs_text = any(
        isinstance(locator, (LineRangeLocator, JsonPointerLocator))
        or isinstance(locator, PageLocator) and source_format is not SourceFormat.PDF
        for locator in locators
    )
    text: str | None = None
    text_error: ValueError | None = None
    if needs_text:
        try:
            text = content.decode("utf-8")
        except ValueError as exc:
            text_error = exc
    lines = (
        tuple(text.splitlines())
        if text is not None
        and any(isinstance(locator, LineRangeLocator) for locator in locators)
        else None
    )
    marked_pages = (
        _marked_pages(text)
        if text is not None
        and any(isinstance(locator, PageLocator) for locator in locators)
        else None
    )

    structured: Any = _UNPREPARED
    structured_error: ValueError | None = None
    if text is not None and any(
        isinstance(locator, JsonPointerLocator) for locator in locators
    ):
        try:
            structured = (
                yaml.safe_load(text)
                if source_format is SourceFormat.OPENAPI_YAML
                else json.loads(text)
            )
        except ValueError as exc:
            structured_error = exc

    pdf_pages: dict[int, str] | None = None
    if source_format is SourceFormat.PDF:
        requested_pages = {
            locator.page for locator in locators if isinstance(locator, PageLocator)
        }
        if requested_pages:
            pdf_pages = {}
            document = pymupdf.open(stream=content, filetype="pdf")
            try:
                for page in sorted(requested_pages):
                    if page <= document.page_count:
                        pdf_pages[page] = normalize_excerpt(
                            document.load_page(page - 1).get_text()
                        )
            finally:
                document.close()

    return _PreparedSource(
        content_digest=hashlib.sha256(content).hexdigest(),
        lines=lines,
        marked_pages=marked_pages,
        pdf_pages=pdf_pages,
        structured=structured,
        text_error=text_error,
        structured_error=structured_error,
    )


def _marked_pages(text: str) -> dict[int, str]:
    pages: dict[int, list[str]] = {}
    current: int | None = None
    for line in text.splitlines():
        if match := _PAGE_MARKER.match(line):
            current = int(match.group("page"))
            pages.setdefault(current, [])
        elif current is not None:
            pages[current].append(line)
    return {
        page: normalize_excerpt("\n".join(lines))
        for page, lines in pages.items()
    }


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
    """A remote snapshot has no manifest entry to read its format from, so it is
    classified the same way `manifest` classifies a local file.

    This used to be a third extension table with its own rules and an
    everything-else-is-Markdown fallback, which labelled an imported `.html`
    snapshot as Markdown (#115). No caller could observe that: `_prepare_source`
    reads the format only to open a PDF's pages and to pick YAML over JSON, and
    `import-rendered-url` accepts only HTML and Markdown. It was a wrong value
    that happened not to be read — the kind that stops being harmless the moment
    someone adds a branch for it.
    """
    return detect_format(Path(path))
