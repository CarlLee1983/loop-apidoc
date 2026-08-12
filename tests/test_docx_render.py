from __future__ import annotations

from xml.etree import ElementTree

import pytest

from loop_apidoc.docx_models import DocxNormalizationError
from loop_apidoc.docx_render import document_to_markdown


NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _document(body: str) -> ElementTree.Element:
    return ElementTree.fromstring(
        f'<w:document xmlns:w="{NS}"><w:body>{body}</w:body></w:document>'
    )


def test_renders_headings_breaks_tabs_and_wrapped_table_content() -> None:
    document = _document(
        """
        <w:p><w:pPr><w:pStyle w:val="Heading9"/></w:pPr>
          <w:r><w:t>API</w:t><w:tab/><w:t>Guide</w:t><w:br/><w:t>v1</w:t></w:r>
        </w:p>
        <w:tbl>
          <w:tblPr/><w:tblGrid/>
          <w:sdt><w:sdtContent><w:tr><w:trPr/>
            <w:sdt><w:sdtContent><w:tc><w:tcPr/>
              <w:p><w:r><w:t>Name|Key</w:t></w:r></w:p>
              <w:sdt><w:sdtContent><w:p><w:r><w:t>Alias</w:t></w:r></w:p></w:sdtContent></w:sdt>
            </w:tc></w:sdtContent></w:sdt>
            <w:tc><w:p><w:r><w:t>Type</w:t></w:r></w:p></w:tc>
          </w:tr></w:sdtContent></w:sdt>
          <w:tr><w:tc><w:p><w:r><w:t>id</w:t></w:r></w:p></w:tc></w:tr>
        </w:tbl>
        """
    )

    assert document_to_markdown(document) == (
        "###### API\tGuide\nv1\n\n"
        "| Name\\|Key<br>Alias | Type |\n"
        "| --- | --- |\n"
        "| id |  |\n"
    )


def test_renders_body_content_control_and_ignores_empty_controls() -> None:
    document = _document(
        """
        <w:sdt><w:sdtContent><w:p><w:r><w:t>Wrapped</w:t></w:r></w:p></w:sdtContent></w:sdt>
        <w:sdt/><w:sectPr/>
        """
    )

    assert document_to_markdown(document) == "Wrapped\n"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("", "has no body"),
        (
            "<w:p><w:r><w:drawing/></w:r></w:p>",
            "paragraph object is unsupported",
        ),
        (
            "<w:tbl><w:sdt><w:r><w:t>x</w:t></w:r></w:sdt></w:tbl>",
            "table content control is unsupported",
        ),
        (
            "<w:tbl><w:tr><w:sdt><w:r><w:t>x</w:t></w:r></w:sdt></w:tr></w:tbl>",
            "row content control is unsupported",
        ),
        (
            "<w:tbl><w:tr><w:tc><w:sdt><w:r><w:t>x</w:t></w:r></w:sdt></w:tc></w:tr></w:tbl>",
            "cell content control is unsupported",
        ),
        (
            "<w:sdt><w:r><w:t>x</w:t></w:r></w:sdt>",
            "content control is unsupported",
        ),
        (
            "<w:custom><w:r><w:t>x</w:t></w:r></w:custom>",
            "body structure is unsupported",
        ),
        (
            "<w:tbl><w:tr><w:tc><w:tbl/></w:tc></w:tr></w:tbl>",
            "nested table is unsupported",
        ),
    ],
)
def test_rejects_unsupported_document_structures(body: str, message: str) -> None:
    if body:
        document = _document(body)
    else:
        document = ElementTree.fromstring(f'<w:document xmlns:w="{NS}"/>')

    with pytest.raises(DocxNormalizationError, match=message):
        document_to_markdown(document)
