from __future__ import annotations

import io
import struct
import zipfile

import pytest

from loop_apidoc.docx_models import DocxNormalizationError
from loop_apidoc.docx_validation import validate_docx_package


CONTENT_TYPES = """<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

ROOT_RELS = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOCUMENT = """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>API</w:t></w:r></w:p></w:body>
</w:document>"""


def _docx(
    *,
    content_types: str = CONTENT_TYPES,
    root_rels: str = ROOT_RELS,
    document: str = DOCUMENT,
    entries: dict[str, bytes | str] | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", compression=compression) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("word/document.xml", document)
        for name, payload in (entries or {}).items():
            archive.writestr(name, payload)
    return raw.getvalue()


def _expect_rejected(raw: bytes, code: str) -> None:
    with pytest.raises(DocxNormalizationError, match=code):
        validate_docx_package(raw)


@pytest.mark.parametrize(
    ("entries", "expected_code"),
    [
        ({"word/activex/control.bin": b"active"}, "DOCX-ACTIVE-CONTENT"),
        ({"word/embeddings/object.bin": b"active"}, "DOCX-ACTIVE-CONTENT"),
        ({"word/media/image.bin": b"media"}, "DOCX-UNSUPPORTED-CONTENT"),
        ({"word/charts/chart.bin": b"chart"}, "DOCX-UNSUPPORTED-CONTENT"),
    ],
)
def test_validate_docx_package_rejects_embedded_content(
    entries: dict[str, bytes], expected_code: str
) -> None:
    _expect_rejected(_docx(entries=entries), expected_code)


@pytest.mark.parametrize(
    ("raw", "expected_code"),
    [
        (b"not-a-zip", "input is not a readable DOCX package"),
    ],
)
def test_validate_docx_package_rejects_unreadable_or_oversized_archives(
    raw: bytes, expected_code: str
) -> None:
    _expect_rejected(raw, expected_code)


def test_validate_docx_package_rejects_oversized_member_before_content_scan() -> None:
    _expect_rejected(
        _docx(
            entries={"word/custom.bin": b"x" * (10 * 1024 * 1024 + 1)},
            compression=zipfile.ZIP_STORED,
        ),
        "DOCX-ZIP-MEMBER-SIZE",
    )


def test_validate_docx_package_rejects_total_archive_size_before_content_scan() -> None:
    _expect_rejected(
        _docx(
            entries={
                f"word/custom-{index}.bin": b"x" * (9 * 1024 * 1024)
                for index in range(6)
            },
            compression=zipfile.ZIP_STORED,
        ),
        "DOCX-ZIP-TOTAL-SIZE",
    )


def test_validate_docx_package_rejects_unsupported_compression() -> None:
    _expect_rejected(
        _docx(entries={"word/custom.bin": b"x"}, compression=zipfile.ZIP_BZIP2),
        "DOCX-ZIP-COMPRESSION",
    )


def test_validate_docx_package_rejects_encrypted_member_flag() -> None:
    raw = bytearray(_docx())
    central_directory = raw.index(b"PK\x01\x02")
    flag_offset = central_directory + 8
    original_flags = struct.unpack_from("<H", raw, flag_offset)[0]
    struct.pack_into("<H", raw, flag_offset, original_flags | 0x1)

    _expect_rejected(bytes(raw), "DOCX-ZIP-ENCRYPTED")


def test_validate_docx_package_rejects_casefolded_duplicate_member_names() -> None:
    _expect_rejected(
        _docx(entries={"word/duplicate.xml": "<part/>", "WORD/DUPLICATE.XML": "<part/>"}),
        "DOCX-ZIP-DUPLICATE",
    )


@pytest.mark.parametrize(
    ("entries", "expected_code"),
    [
        ({"word/_rels/missing.xml.rels": ROOT_RELS}, "DOCX-OPC-RELATIONSHIP"),
        ({"word/document.xml.rels": ROOT_RELS}, "DOCX-OPC-RELATIONSHIP"),
    ],
)
def test_validate_docx_package_rejects_invalid_relationship_part_paths(
    entries: dict[str, str], expected_code: str
) -> None:
    _expect_rejected(_docx(entries=entries), expected_code)


@pytest.mark.parametrize(
    ("relationships", "expected_code"),
    [
        ("<not-relationships/>", "DOCX-OPC-RELATIONSHIP"),
        (
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
            <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
            <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
            </Relationships>""",
            "DOCX-OPC-RELATIONSHIP",
        ),
        (
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
            <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="../outside.xml"/>
            </Relationships>""",
            "DOCX-OPC-TARGET",
        ),
        (
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
            <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="missing.xml"/>
            </Relationships>""",
            "DOCX-OPC-TARGET",
        ),
        (
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
            <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml" TargetMode="Other"/>
            </Relationships>""",
            "DOCX-OPC-RELATIONSHIP",
        ),
        (
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
            <Unexpected/>
            </Relationships>""",
            "DOCX-OPC-RELATIONSHIP",
        ),
        (
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
            <Relationship Id="rId1" Target="styles.xml"/>
            </Relationships>""",
            "DOCX-OPC-RELATIONSHIP",
        ),
        (
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
            <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="object.bin"/>
            </Relationships>""",
            "DOCX-ACTIVE-CONTENT",
        ),
    ],
)
def test_validate_docx_package_rejects_unsafe_relationships(
    relationships: str, expected_code: str
) -> None:
    _expect_rejected(_docx(entries={"word/_rels/document.xml.rels": relationships,
                                   "word/styles.xml": "<styles/>"}), expected_code)


def test_validate_docx_package_accepts_absolute_internal_relationship_target() -> None:
    relationships = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="/word/styles.xml"/>
    </Relationships>"""
    document = validate_docx_package(
        _docx(
            entries={
                "word/_rels/document.xml.rels": relationships,
                "word/styles.xml": "<styles/>",
            }
        )
    )

    assert document.tag.endswith("}document")


@pytest.mark.parametrize(
    ("content_types", "expected_code"),
    [
        ("<Types/>", "DOCX-OPC-CONTENT-TYPE"),
        (
            CONTENT_TYPES.replace(
                'ContentType="application/xml"',
                'ContentType="application/vnd.ms-word.document.macroEnabled.12"',
            ),
            "DOCX-ACTIVE-CONTENT",
        ),
        (
            CONTENT_TYPES.replace(
                '<Default Extension="xml" ContentType="application/xml"/>',
                '<Default Extension="xml" ContentType="application/xml"/>\n'
                '<Default Extension="XML" ContentType="application/xml"/>',
            ),
            "DOCX-OPC-CONTENT-TYPE",
        ),
        (
            CONTENT_TYPES.replace(
                "document.main+xml", "template.main+xml"
            ),
            "DOCX-OPC-CONTENT-TYPE",
        ),
        (
            CONTENT_TYPES.replace('ContentType="application/xml"', ""),
            "DOCX-OPC-CONTENT-TYPE",
        ),
        (
            CONTENT_TYPES.replace('PartName="/word/document.xml"', 'PartName="word/document.xml"'),
            "DOCX-OPC-CONTENT-TYPE",
        ),
        (
            CONTENT_TYPES.replace("</Types>", "<Unexpected xmlns=\"\"/></Types>"),
            "DOCX-OPC-CONTENT-TYPE",
        ),
    ],
)
def test_validate_docx_package_rejects_invalid_content_type_contract(
    content_types: str, expected_code: str
) -> None:
    _expect_rejected(_docx(content_types=content_types), expected_code)


def test_validate_docx_package_rejects_part_without_declared_content_type() -> None:
    content_types = CONTENT_TYPES.replace(
        '<Default Extension="xml" ContentType="application/xml"/>\n', ""
    )
    _expect_rejected(
        _docx(content_types=content_types, entries={"word/custom.xml": "<part/>"}),
        "DOCX-OPC-CONTENT-TYPE",
    )


def test_validate_docx_package_rejects_missing_required_part() -> None:
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
    _expect_rejected(raw.getvalue(), "DOCX-OPC-REQUIRED")


def test_validate_docx_package_rejects_invalid_root_document_relationship() -> None:
    _expect_rejected(
        _docx(
            root_rels=ROOT_RELS.replace(
                'Target="word/document.xml"', 'Target="wrong.xml"'
            ),
            entries={"wrong.xml": "<part/>"},
        ),
        "DOCX-OPC-ROOT",
    )


@pytest.mark.parametrize(
    ("document", "entries", "expected_code"),
    [
        (DOCUMENT, {"word/header1.xml": "<w:hdr>"}, "DOCX-XML-INVALID"),
        (
            "<w:notDocument xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"/>",
            None,
            "DOCX-XML-DOCUMENT",
        ),
        (
            DOCUMENT,
            {
                "word/header1.xml": """<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:p><w:r><w:t>Visible header</w:t></w:r></w:p></w:hdr>"""
            },
            "DOCX-UNSUPPORTED-CONTENT",
        ),
        (
            DOCUMENT,
            {
                "word/footer1.xml": """<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:tbl/></w:ftr>"""
            },
            "DOCX-UNSUPPORTED-CONTENT",
        ),
    ],
)
def test_validate_docx_package_rejects_unsupported_word_parts(
    document: str, entries: dict[str, str] | None, expected_code: str
) -> None:
    _expect_rejected(_docx(document=document, entries=entries), expected_code)
