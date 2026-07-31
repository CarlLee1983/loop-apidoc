"""Pure, fail-closed validation for in-memory OOXML Word packages."""

from __future__ import annotations

import io
import posixpath
import re
import unicodedata
import zipfile
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from loop_apidoc.docx_models import DocxNormalizationError


SECURITY_POLICY_VERSION = "2"
MAX_COMPRESSION_RATIO = 100
MAX_ARCHIVE_ENTRIES = 2048
MAX_MEMBER_BYTES = 10 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_CONTENT_TYPES = "{http://schemas.openxmlformats.org/package/2006/content-types}"
_MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
_OFFICE_DOCUMENT_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)
_DOCX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
_ACTIVE_MARKERS = ("activex", "macroenabled", "oleobject", "vbaproject")
_DDE_FIELD = re.compile(r"(?:^|\s)DDE(?:AUTO)?(?:\s|$)", re.IGNORECASE)
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
            raise DocxNormalizationError(
                "DOCX-ZIP-ENCRYPTED: encrypted members are forbidden"
            )
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
        raise DocxNormalizationError(
            "DOCX-XML-DECLARATION: DTD and entities are forbidden"
        )
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


def contains_material_content(root: ElementTree.Element) -> bool:
    if any(node.text and node.text.strip() for node in root.iter(f"{WORD_NAMESPACE}t")):
        return True
    material_tags = {
        f"{WORD_NAMESPACE}tbl",
        f"{WORD_NAMESPACE}altChunk",
        f"{WORD_NAMESPACE}object",
        f"{WORD_NAMESPACE}drawing",
        f"{WORD_NAMESPACE}pict",
    }
    return any(node.tag in material_tags for node in root.iter())


def _validate_protected_word_semantics(
    name: str,
    root: ElementTree.Element,
) -> None:
    """Reject protected semantics anywhere in a Word XML part before rendering."""
    lowered_name = name.casefold()
    if not lowered_name.startswith("word/") or not lowered_name.endswith(".xml"):
        return

    simple_fields = (
        node.get(f"{WORD_NAMESPACE}instr", "")
        for node in root.iter(f"{WORD_NAMESPACE}fldSimple")
    )
    paragraph_fields = (
        "".join(
            node.text or ""
            for node in paragraph.iter(f"{WORD_NAMESPACE}instrText")
        )
        for paragraph in root.iter(f"{WORD_NAMESPACE}p")
    )
    standalone_fields = (
        node.text or "" for node in root.iter(f"{WORD_NAMESPACE}instrText")
    )
    if any(
        _DDE_FIELD.search(instruction)
        for instructions in (simple_fields, paragraph_fields, standalone_fields)
        for instruction in instructions
    ):
        raise DocxNormalizationError(
            "DOCX-ACTIVE-CONTENT: active field code is forbidden"
        )
    if any(node.tag == f"{_MC}AlternateContent" for node in root.iter()):
        raise DocxNormalizationError(
            "DOCX-UNSUPPORTED-CONTENT: alternate markup is unsupported"
        )
    merged_tags = {
        f"{WORD_NAMESPACE}gridSpan",
        f"{WORD_NAMESPACE}vMerge",
    }
    if any(node.tag in merged_tags for node in root.iter()):
        raise DocxNormalizationError(
            "DOCX-UNSUPPORTED-CONTENT: merged table cells are unsupported"
        )


def _validate_package_xml(parts: dict[str, bytes]) -> ElementTree.Element:
    required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
    if not required.issubset(parts):
        raise DocxNormalizationError(
            "DOCX-OPC-REQUIRED: required package part is missing"
        )

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
    for name, root in parsed.items():
        _validate_protected_word_semantics(name, root)
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
                "word/commentsextended.xml",
                "word/glossary/document.xml",
            }
        ) and contains_material_content(root):
            raise DocxNormalizationError(
                "DOCX-UNSUPPORTED-CONTENT: visible Word part is unsupported"
            )

    document = parsed["word/document.xml"]
    if document.tag != f"{WORD_NAMESPACE}document":
        raise DocxNormalizationError("DOCX-XML-DOCUMENT: document root is invalid")
    if document.find(f".//{WORD_NAMESPACE}altChunk") is not None:
        raise DocxNormalizationError("DOCX-ALTCHUNK: alternate content is forbidden")
    return document


def validate_docx_package(raw: bytes) -> ElementTree.Element:
    """Validate an in-memory DOCX package and return its document element."""
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
            return _validate_package_xml(parts)
    except DocxNormalizationError:
        raise
    except (KeyError, zipfile.BadZipFile, OSError) as exc:
        raise DocxNormalizationError("input is not a readable DOCX package") from exc
