from __future__ import annotations

from pathlib import Path

from loop_apidoc.manifest.formats import detect_format, is_supported
from loop_apidoc.manifest.models import SourceFormat


def test_detect_pdf_is_case_insensitive():
    assert detect_format(Path("spec.PDF")) is SourceFormat.PDF


def test_detect_markdown_variants():
    assert detect_format(Path("guide.md")) is SourceFormat.MARKDOWN
    assert detect_format(Path("guide.markdown")) is SourceFormat.MARKDOWN


def test_detect_word_and_openapi():
    assert detect_format(Path("notes.docx")) is SourceFormat.WORD
    assert detect_format(Path("api.json")) is SourceFormat.OPENAPI_JSON
    assert detect_format(Path("api.yaml")) is SourceFormat.OPENAPI_YAML
    assert detect_format(Path("api.yml")) is SourceFormat.OPENAPI_YAML


def test_detect_unknown_extension():
    assert detect_format(Path("notes.txt")) is SourceFormat.UNKNOWN


def test_is_supported():
    assert is_supported(SourceFormat.WORD) is True
    assert is_supported(SourceFormat.UNKNOWN) is False
