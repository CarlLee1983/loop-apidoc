"""Pure DOCX document rendering after package validation."""

from __future__ import annotations

from xml.etree import ElementTree

from loop_apidoc.docx_models import DocxNormalizationError
from loop_apidoc.docx_validation import WORD_NAMESPACE, contains_material_content


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == f"{WORD_NAMESPACE}t" and node.text:
            parts.append(node.text)
        elif node.tag == f"{WORD_NAMESPACE}tab":
            parts.append("\t")
        elif node.tag in {f"{WORD_NAMESPACE}br", f"{WORD_NAMESPACE}cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def _validate_paragraph_content(paragraph: ElementTree.Element) -> None:
    forbidden = {
        f"{WORD_NAMESPACE}altChunk",
        f"{WORD_NAMESPACE}drawing",
        f"{WORD_NAMESPACE}object",
        f"{WORD_NAMESPACE}pict",
    }
    if any(node.tag in forbidden for node in paragraph.iter()):
        raise DocxNormalizationError(
            "DOCX-UNSUPPORTED-CONTENT: paragraph object is unsupported"
        )


def _render_paragraph(paragraph: ElementTree.Element) -> str:
    _validate_paragraph_content(paragraph)
    value = _paragraph_text(paragraph)
    if not value:
        return ""
    style = paragraph.find(f"{WORD_NAMESPACE}pPr/{WORD_NAMESPACE}pStyle")
    style_name = style.get(f"{WORD_NAMESPACE}val", "") if style is not None else ""
    if style_name.lower().startswith("heading"):
        suffix = style_name[len("Heading") :]
        level = int(suffix) if suffix.isdigit() else 1
        return f"{'#' * min(max(level, 1), 6)} {value}"
    return value


def _render_table(table: ElementTree.Element) -> str:
    def rows_in(container: ElementTree.Element) -> list[ElementTree.Element]:
        found: list[ElementTree.Element] = []
        for child in container:
            if child.tag == f"{WORD_NAMESPACE}tr":
                found.append(child)
            elif child.tag == f"{WORD_NAMESPACE}sdt":
                content = child.find(f"{WORD_NAMESPACE}sdtContent")
                if content is None:
                    if contains_material_content(child):
                        raise DocxNormalizationError(
                            "DOCX-UNSUPPORTED-CONTENT: "
                            "table content control is unsupported"
                        )
                else:
                    found.extend(rows_in(content))
            elif child.tag not in {
                f"{WORD_NAMESPACE}tblPr",
                f"{WORD_NAMESPACE}tblGrid",
            } and contains_material_content(child):
                raise DocxNormalizationError(
                    "DOCX-UNSUPPORTED-CONTENT: table structure is unsupported"
                )
        return found

    def cell_paragraphs(container: ElementTree.Element) -> list[str]:
        found: list[str] = []
        for child in container:
            if child.tag == f"{WORD_NAMESPACE}p":
                _validate_paragraph_content(child)
                if value := _paragraph_text(child):
                    found.append(value)
            elif child.tag == f"{WORD_NAMESPACE}sdt":
                content = child.find(f"{WORD_NAMESPACE}sdtContent")
                if content is None:
                    if contains_material_content(child):
                        raise DocxNormalizationError(
                            "DOCX-UNSUPPORTED-CONTENT: "
                            "cell content control is unsupported"
                        )
                else:
                    found.extend(cell_paragraphs(content))
            elif (
                child.tag != f"{WORD_NAMESPACE}tcPr"
                and contains_material_content(child)
            ):
                raise DocxNormalizationError(
                    "DOCX-UNSUPPORTED-CONTENT: table cell structure is unsupported"
                )
        return found

    def cells_in(container: ElementTree.Element) -> list[ElementTree.Element]:
        found: list[ElementTree.Element] = []
        for child in container:
            if child.tag == f"{WORD_NAMESPACE}tc":
                found.append(child)
            elif child.tag == f"{WORD_NAMESPACE}sdt":
                content = child.find(f"{WORD_NAMESPACE}sdtContent")
                if content is None:
                    if contains_material_content(child):
                        raise DocxNormalizationError(
                            "DOCX-UNSUPPORTED-CONTENT: "
                            "row content control is unsupported"
                        )
                else:
                    found.extend(cells_in(content))
            elif (
                child.tag != f"{WORD_NAMESPACE}trPr"
                and contains_material_content(child)
            ):
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


def document_to_markdown(document: ElementTree.Element) -> str:
    """Render a validated Word document element as source-faithful Markdown."""
    body = document.find(f"{WORD_NAMESPACE}body")
    if body is None:
        raise DocxNormalizationError("DOCX document.xml has no body")

    def render_blocks(container: ElementTree.Element) -> list[str]:
        rendered_blocks: list[str] = []
        for child in container:
            if child.tag == f"{WORD_NAMESPACE}p":
                rendered = _render_paragraph(child)
                if rendered:
                    rendered_blocks.append(rendered)
            elif child.tag == f"{WORD_NAMESPACE}tbl":
                if child.find(f".//{WORD_NAMESPACE}tbl") is not None:
                    raise DocxNormalizationError(
                        "DOCX-UNSUPPORTED-CONTENT: nested table is unsupported"
                    )
                rendered = _render_table(child)
                if rendered:
                    rendered_blocks.append(rendered)
            elif child.tag == f"{WORD_NAMESPACE}sdt":
                content = child.find(f"{WORD_NAMESPACE}sdtContent")
                if content is None:
                    if contains_material_content(child):
                        raise DocxNormalizationError(
                            "DOCX-UNSUPPORTED-CONTENT: content control is unsupported"
                        )
                    continue
                rendered_blocks.extend(render_blocks(content))
            elif (
                child.tag != f"{WORD_NAMESPACE}sectPr"
                and contains_material_content(child)
            ):
                raise DocxNormalizationError(
                    "DOCX-UNSUPPORTED-CONTENT: body structure is unsupported"
                )
        return rendered_blocks

    blocks = render_blocks(body)
    return "\n\n".join(blocks) + ("\n" if blocks else "")
