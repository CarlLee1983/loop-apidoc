"""Securely normalize one OOXML Word document into auditable Markdown."""

from __future__ import annotations

import hashlib
import io
import json
import os
import posixpath
import re
import stat
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree


SECURITY_POLICY_VERSION = "1"
MAX_COMPRESSION_RATIO = 100
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2048
MAX_MEMBER_BYTES = 10 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_CONTENT_TYPES = "{http://schemas.openxmlformats.org/package/2006/content-types}"
_OFFICE_DOCUMENT_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)
_DOCX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
_ACTIVE_MARKERS = ("activex", "macroenabled", "oleobject", "vbaproject")
_ALLOWED_RELATIONSHIP_SUFFIXES = (
    "/core-properties",
    "/custom-properties",
    "/customxml",
    "/customxmlprops",
    "/extended-properties",
    "/fonttable",
    "/numbering",
    "/officedocument",
    "/settings",
    "/styles",
    "/styleswitheffects",
    "/theme",
    "/thumbnail",
    "/websettings",
)


class DocxNormalizationError(ValueError):
    """A DOCX source cannot be normalized safely and completely."""


@dataclass(frozen=True)
class DocxNormalizationResult:
    output: Path
    provenance: Path


@dataclass(frozen=True)
class PreparedDocx:
    markdown: bytes
    provenance: dict[str, object]


def _validate_archive_name(name: str) -> None:
    normalized = name[:-1] if name.endswith("/") else name
    parts = normalized.split("/")
    if (
        not normalized
        or name.startswith("/")
        or "\\" in name
        or "\x00" in name
        or re.match(r"^[A-Za-z]:", name)
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise DocxNormalizationError("DOCX-ZIP-PATH: unsafe archive member")


def _read_source(input_file: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow and input_file.is_symlink():
        raise DocxNormalizationError("DOCX-SOURCE-TYPE: source must be a regular file")
    try:
        descriptor = os.open(input_file, flags | nofollow)
    except OSError as exc:
        raise DocxNormalizationError("input is not a readable DOCX package") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise DocxNormalizationError(
                "DOCX-SOURCE-TYPE: source must be a regular file"
            )
        if metadata.st_size > MAX_ARCHIVE_BYTES:
            raise DocxNormalizationError("DOCX-ZIP-SIZE: archive exceeds policy")
        chunks: list[bytes] = []
        remaining = MAX_ARCHIVE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_ARCHIVE_BYTES:
            raise DocxNormalizationError("DOCX-ZIP-SIZE: archive exceeds policy")
        return raw
    except OSError as exc:
        raise DocxNormalizationError("input is not a readable DOCX package") from exc
    finally:
        os.close(descriptor)


def _validate_archive(infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise DocxNormalizationError("DOCX-ZIP-ENTRIES: archive exceeds policy")
    total_size = 0
    seen_names: set[str] = set()
    for info in infos:
        _validate_archive_name(info.filename)
        normalized_name = unicodedata.normalize("NFC", info.filename).casefold()
        if normalized_name in seen_names:
            raise DocxNormalizationError("DOCX-ZIP-DUPLICATE: duplicate archive member")
        seen_names.add(normalized_name)
        if info.flag_bits & 0x1:
            raise DocxNormalizationError("DOCX-ZIP-ENCRYPTED: encrypted members are forbidden")
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise DocxNormalizationError(
                "DOCX-ZIP-COMPRESSION: unsupported compression method"
            )
        if info.file_size > MAX_MEMBER_BYTES:
            raise DocxNormalizationError("DOCX-ZIP-MEMBER-SIZE: member exceeds policy")
        total_size += info.file_size
        if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise DocxNormalizationError("DOCX-ZIP-TOTAL-SIZE: archive exceeds policy")
        if (
            not info.is_dir()
            and info.file_size
            and (
                info.compress_size == 0
                or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            )
        ):
            raise DocxNormalizationError(
                "DOCX-ZIP-RATIO: compression ratio exceeds policy"
            )


def _parse_xml(payload: bytes) -> ElementTree.Element:
    if payload.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in payload:
        raise DocxNormalizationError(
            "DOCX-XML-ENCODING: only UTF-8-compatible package XML is supported"
        )
    lowered = payload.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise DocxNormalizationError("DOCX-XML-DECLARATION: DTD and entities are forbidden")
    try:
        return ElementTree.fromstring(payload)
    except (ElementTree.ParseError, LookupError) as exc:
        raise DocxNormalizationError("DOCX-XML-INVALID: package XML is invalid") from exc


def _relationship_source(name: str, parts: dict[str, bytes]) -> PurePosixPath | None:
    if name == "_rels/.rels":
        return None
    relationship_path = PurePosixPath(name)
    if relationship_path.parent.name != "_rels" or not name.endswith(".rels"):
        raise DocxNormalizationError(
            "DOCX-OPC-RELATIONSHIP: relationship part path is invalid"
        )
    source_name = relationship_path.name[: -len(".rels")]
    source = relationship_path.parent.parent / source_name
    if source.as_posix() not in parts:
        raise DocxNormalizationError(
            "DOCX-OPC-RELATIONSHIP: relationship source part is missing"
        )
    return source


def _resolve_relationship_target(
    source: PurePosixPath | None, target: str, parts: dict[str, bytes]
) -> str:
    decoded = unquote(target)
    parsed_target = urlsplit(decoded)
    if (
        not decoded
        or "\\" in decoded
        or "\x00" in decoded
        or parsed_target.scheme
        or parsed_target.netloc
        or parsed_target.query
        or parsed_target.fragment
        or ".." in PurePosixPath(parsed_target.path).parts
    ):
        raise DocxNormalizationError(
            "DOCX-OPC-TARGET: internal relationship target is unsafe"
        )
    if parsed_target.path.startswith("/"):
        candidate = parsed_target.path.lstrip("/")
    else:
        base = source.parent.as_posix() if source is not None else ""
        candidate = posixpath.normpath(posixpath.join(base, parsed_target.path))
    if candidate.startswith("../") or candidate not in parts:
        raise DocxNormalizationError(
            "DOCX-OPC-TARGET: internal relationship target is missing"
        )
    return candidate


def _validate_relationships(
    parsed: dict[str, ElementTree.Element], parts: dict[str, bytes]
) -> None:
    for name, root in parsed.items():
        if not name.casefold().endswith(".rels"):
            continue
        if root.tag != f"{_REL}Relationships":
            raise DocxNormalizationError(
                "DOCX-OPC-RELATIONSHIP: relationship XML root is invalid"
            )
        source = _relationship_source(name, parts)
        seen_ids: set[str] = set()
        for node in root:
            if node.tag != f"{_REL}Relationship":
                raise DocxNormalizationError(
                    "DOCX-OPC-RELATIONSHIP: relationship entry is invalid"
                )
            relationship_id = node.get("Id", "")
            if not relationship_id or relationship_id in seen_ids:
                raise DocxNormalizationError(
                    "DOCX-OPC-RELATIONSHIP: relationship ID is missing or duplicate"
                )
            seen_ids.add(relationship_id)
            relationship_type = node.get("Type", "")
            if not relationship_type:
                raise DocxNormalizationError(
                    "DOCX-OPC-RELATIONSHIP: relationship type is missing"
                )
            mode = node.get("TargetMode", "Internal")
            if mode.casefold() == "external":
                raise DocxNormalizationError(
                    "DOCX-EXTERNAL-RELATIONSHIP: external relationships are forbidden"
                )
            if mode.casefold() != "internal":
                raise DocxNormalizationError(
                    "DOCX-OPC-RELATIONSHIP: relationship mode is unsupported"
                )
            if any(
                marker in relationship_type.casefold() for marker in _ACTIVE_MARKERS
            ):
                raise DocxNormalizationError(
                    "DOCX-ACTIVE-CONTENT: active relationship is forbidden"
                )
            if not relationship_type.casefold().endswith(
                _ALLOWED_RELATIONSHIP_SUFFIXES
            ):
                raise DocxNormalizationError(
                    "DOCX-UNSUPPORTED-CONTENT: relationship type is unsupported"
                )
            _resolve_relationship_target(source, node.get("Target", ""), parts)


def _validate_content_types(
    content_types: ElementTree.Element, parts: dict[str, bytes]
) -> None:
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for node in content_types:
        content_type = node.get("ContentType", "")
        if not content_type:
            raise DocxNormalizationError(
                "DOCX-OPC-CONTENT-TYPE: content type is missing"
            )
        if any(marker in content_type.casefold() for marker in _ACTIVE_MARKERS):
            raise DocxNormalizationError(
                "DOCX-ACTIVE-CONTENT: active content type is forbidden"
            )
        if node.tag == f"{_CONTENT_TYPES}Default":
            extension = node.get("Extension", "").casefold()
            if not extension or extension in defaults:
                raise DocxNormalizationError(
                    "DOCX-OPC-CONTENT-TYPE: default entry is invalid"
                )
            defaults[extension] = content_type
        elif node.tag == f"{_CONTENT_TYPES}Override":
            part_name = node.get("PartName", "")
            normalized = part_name.lstrip("/")
            if (
                not part_name.startswith("/")
                or not normalized
                or normalized in overrides
            ):
                raise DocxNormalizationError(
                    "DOCX-OPC-CONTENT-TYPE: override entry is invalid"
                )
            overrides[normalized] = content_type
        else:
            raise DocxNormalizationError(
                "DOCX-OPC-CONTENT-TYPE: content type entry is invalid"
            )

    for name in parts:
        if name == "[Content_Types].xml":
            continue
        extension = (
            "rels"
            if name.casefold().endswith(".rels")
            else PurePosixPath(name).suffix.lstrip(".").casefold()
        )
        if name not in overrides and extension not in defaults:
            raise DocxNormalizationError(
                "DOCX-OPC-CONTENT-TYPE: package part has no content type"
            )


def _contains_material_content(root: ElementTree.Element) -> bool:
    if any(node.text and node.text.strip() for node in root.iter(f"{_W}t")):
        return True
    material_tags = {
        f"{_W}tbl",
        f"{_W}altChunk",
        f"{_W}object",
        f"{_W}drawing",
        f"{_W}pict",
    }
    return any(node.tag in material_tags for node in root.iter())


def _validate_package_xml(parts: dict[str, bytes]) -> ElementTree.Element:
    required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
    if not required.issubset(parts):
        raise DocxNormalizationError("DOCX-OPC-REQUIRED: required package part is missing")

    parsed = {
        name: _parse_xml(payload)
        for name, payload in parts.items()
        if name.casefold().endswith((".xml", ".rels"))
    }
    content_types = parsed["[Content_Types].xml"]
    if content_types.tag != f"{_CONTENT_TYPES}Types":
        raise DocxNormalizationError(
            "DOCX-OPC-CONTENT-TYPE: content-types root is invalid"
        )
    _validate_content_types(content_types, parts)
    if not any(
        node.get("PartName") == "/word/document.xml"
        and node.get("ContentType") == _DOCX_MAIN_CONTENT_TYPE
        for node in content_types.findall(f"{_CONTENT_TYPES}Override")
    ):
        raise DocxNormalizationError(
            "DOCX-OPC-CONTENT-TYPE: document content type is unsupported"
        )

    _validate_relationships(parsed, parts)
    root_relationships = parsed["_rels/.rels"]
    office_relationships = [
        node
        for node in root_relationships.findall(f"{_REL}Relationship")
        if node.get("Type") == _OFFICE_DOCUMENT_REL
    ]
    if not (
        len(office_relationships) == 1
        and office_relationships[0].get("Target") == "word/document.xml"
        and office_relationships[0].get("TargetMode", "Internal").casefold()
        == "internal"
    ):
        raise DocxNormalizationError(
            "DOCX-OPC-ROOT: package document relationship is invalid"
        )

    for name, root in parsed.items():
        lowered_name = name.casefold()
        if (
            re.fullmatch(r"word/(header|footer)\d*\.xml", lowered_name)
            or lowered_name
            in {
                "word/footnotes.xml",
                "word/endnotes.xml",
                "word/comments.xml",
                "word/commentsExtended.xml".casefold(),
                "word/glossary/document.xml",
            }
        ) and _contains_material_content(root):
            raise DocxNormalizationError(
                "DOCX-UNSUPPORTED-CONTENT: visible Word part is unsupported"
            )

    document = parsed["word/document.xml"]
    if document.tag != f"{_W}document":
        raise DocxNormalizationError("DOCX-XML-DOCUMENT: document root is invalid")
    if document.find(f".//{_W}altChunk") is not None:
        raise DocxNormalizationError("DOCX-ALTCHUNK: alternate content is forbidden")
    return document


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == f"{_W}t" and node.text:
            parts.append(node.text)
        elif node.tag == f"{_W}tab":
            parts.append("\t")
        elif node.tag in {f"{_W}br", f"{_W}cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def _validate_paragraph_content(paragraph: ElementTree.Element) -> None:
    forbidden = {f"{_W}altChunk", f"{_W}drawing", f"{_W}object", f"{_W}pict"}
    if any(node.tag in forbidden for node in paragraph.iter()):
        raise DocxNormalizationError(
            "DOCX-UNSUPPORTED-CONTENT: paragraph object is unsupported"
        )


def _render_paragraph(paragraph: ElementTree.Element) -> str:
    _validate_paragraph_content(paragraph)
    value = _paragraph_text(paragraph)
    if not value:
        return ""
    style = paragraph.find(f"{_W}pPr/{_W}pStyle")
    style_name = style.get(f"{_W}val", "") if style is not None else ""
    if style_name.lower().startswith("heading"):
        suffix = style_name[len("Heading") :]
        level = int(suffix) if suffix.isdigit() else 1
        return f"{'#' * min(max(level, 1), 6)} {value}"
    return value


def _render_table(table: ElementTree.Element) -> str:
    def rows_in(container: ElementTree.Element) -> list[ElementTree.Element]:
        found: list[ElementTree.Element] = []
        for child in container:
            if child.tag == f"{_W}tr":
                found.append(child)
            elif child.tag == f"{_W}sdt":
                content = child.find(f"{_W}sdtContent")
                if content is None:
                    if _contains_material_content(child):
                        raise DocxNormalizationError(
                            "DOCX-UNSUPPORTED-CONTENT: table content control is unsupported"
                        )
                else:
                    found.extend(rows_in(content))
            elif child.tag not in {f"{_W}tblPr", f"{_W}tblGrid"} and (
                _contains_material_content(child)
            ):
                raise DocxNormalizationError(
                    "DOCX-UNSUPPORTED-CONTENT: table structure is unsupported"
                )
        return found

    def cell_paragraphs(container: ElementTree.Element) -> list[str]:
        found: list[str] = []
        for child in container:
            if child.tag == f"{_W}p":
                _validate_paragraph_content(child)
                if value := _paragraph_text(child):
                    found.append(value)
            elif child.tag == f"{_W}sdt":
                content = child.find(f"{_W}sdtContent")
                if content is None:
                    if _contains_material_content(child):
                        raise DocxNormalizationError(
                            "DOCX-UNSUPPORTED-CONTENT: cell content control is unsupported"
                        )
                else:
                    found.extend(cell_paragraphs(content))
            elif child.tag != f"{_W}tcPr" and _contains_material_content(child):
                raise DocxNormalizationError(
                    "DOCX-UNSUPPORTED-CONTENT: table cell structure is unsupported"
                )
        return found

    def cells_in(container: ElementTree.Element) -> list[ElementTree.Element]:
        found: list[ElementTree.Element] = []
        for child in container:
            if child.tag == f"{_W}tc":
                found.append(child)
            elif child.tag == f"{_W}sdt":
                content = child.find(f"{_W}sdtContent")
                if content is None:
                    if _contains_material_content(child):
                        raise DocxNormalizationError(
                            "DOCX-UNSUPPORTED-CONTENT: row content control is unsupported"
                        )
                else:
                    found.extend(cells_in(content))
            elif child.tag != f"{_W}trPr" and _contains_material_content(child):
                raise DocxNormalizationError(
                    "DOCX-UNSUPPORTED-CONTENT: table row structure is unsupported"
                )
        return found

    rows: list[list[str]] = []
    for row in rows_in(table):
        cells: list[str] = []
        for cell in cells_in(row):
            value = "<br>".join(cell_paragraphs(cell))
            cells.append(value.replace("|", r"\|"))
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    header, *body = padded
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def _document_to_markdown(document: ElementTree.Element) -> str:
    body = document.find(f"{_W}body")
    if body is None:
        raise DocxNormalizationError("DOCX document.xml has no body")

    def render_blocks(container: ElementTree.Element) -> list[str]:
        rendered_blocks: list[str] = []
        for child in container:
            if child.tag == f"{_W}p":
                rendered = _render_paragraph(child)
                if rendered:
                    rendered_blocks.append(rendered)
            elif child.tag == f"{_W}tbl":
                if child.find(f".//{_W}tbl") is not None:
                    raise DocxNormalizationError(
                        "DOCX-UNSUPPORTED-CONTENT: nested table is unsupported"
                    )
                rendered = _render_table(child)
                if rendered:
                    rendered_blocks.append(rendered)
            elif child.tag == f"{_W}sdt":
                content = child.find(f"{_W}sdtContent")
                if content is None:
                    if _contains_material_content(child):
                        raise DocxNormalizationError(
                            "DOCX-UNSUPPORTED-CONTENT: content control is unsupported"
                        )
                    continue
                rendered_blocks.extend(render_blocks(content))
            elif child.tag != f"{_W}sectPr" and _contains_material_content(child):
                raise DocxNormalizationError(
                    "DOCX-UNSUPPORTED-CONTENT: body structure is unsupported"
                )
        return rendered_blocks

    blocks = render_blocks(body)
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def prepare_docx(input_file: Path, normalized_name: str) -> PreparedDocx:
    """Validate and render one DOCX fully in memory before any output is written."""
    raw = _read_source(input_file)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            _validate_archive(infos)
            names = [info.filename.casefold() for info in infos]
            if any(name.endswith("vbaproject.bin") for name in names):
                raise DocxNormalizationError("DOCX-MACRO: active content is forbidden")
            if any(
                name.startswith(("word/activex/", "word/embeddings/"))
                for name in names
            ):
                raise DocxNormalizationError(
                    "DOCX-ACTIVE-CONTENT: embedded active content is forbidden"
                )
            if any(
                name.startswith(("word/media/", "word/charts/", "word/diagrams/"))
                for name in names
            ):
                raise DocxNormalizationError(
                    "DOCX-UNSUPPORTED-CONTENT: embedded media is unsupported"
                )
            parts = {
                info.filename: archive.read(info)
                for info in infos
                if not info.is_dir()
            }
            document = _validate_package_xml(parts)
    except DocxNormalizationError:
        raise
    except (KeyError, zipfile.BadZipFile, OSError) as exc:
        raise DocxNormalizationError("input is not a readable DOCX package") from exc

    markdown = _document_to_markdown(document)
    normalized = markdown.encode("utf-8")
    provenance = {
        "schema_version": 1,
        "security_policy_version": SECURITY_POLICY_VERSION,
        "normalizer": "loop-apidoc-docx",
        "source_file": input_file.name,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_size_bytes": len(raw),
        "normalized_file": normalized_name,
        "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
        "normalized_size_bytes": len(normalized),
    }
    return PreparedDocx(markdown=normalized, provenance=provenance)


def write_prepared_docx(
    prepared: PreparedDocx, output: Path
) -> DocxNormalizationResult:
    """Write a previously validated normalization and its provenance sidecar."""
    sidecar = output.with_suffix(output.suffix + ".source.json")
    if output.exists() or sidecar.exists():
        raise DocxNormalizationError("DOCX normalization output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    provenance_bytes = json.dumps(
        prepared.provenance, ensure_ascii=False, indent=2
    ).encode("utf-8")
    output_temp: Path | None = None
    sidecar_temp: Path | None = None
    output_published = False
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as handle:
            output_temp = Path(handle.name)
            handle.write(prepared.markdown)
            handle.flush()
            os.fsync(handle.fileno())
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as handle:
            sidecar_temp = Path(handle.name)
            handle.write(provenance_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        output_temp.replace(output)
        output_published = True
        sidecar_temp.replace(sidecar)
    except OSError:
        if output_published:
            output.unlink(missing_ok=True)
        raise
    finally:
        if output_temp is not None:
            output_temp.unlink(missing_ok=True)
        if sidecar_temp is not None:
            sidecar_temp.unlink(missing_ok=True)
    return DocxNormalizationResult(output=output, provenance=sidecar)


def normalize_docx(input_file: Path, output: Path) -> DocxNormalizationResult:
    """Normalize one DOCX without executing or resolving package relationships."""
    return write_prepared_docx(prepare_docx(input_file, output.name), output)
