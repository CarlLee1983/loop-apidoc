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


def test_legacy_binary_word_is_detected_but_not_supported():
    """認得出格式不等於讀得動。

    `.doc` 是 OLE 複合檔,OOXML 的驗證／渲染路徑對它完全不適用,`preprocess` 也只轉
    `.pdf`/`.docx`。標成 supported 會讓 manifest 宣稱一件不成立的事,而 operator 要到
    `inspect-source-risk` 才發現——那是第三關,前面兩關都在對他說沒問題。
    """
    assert detect_format(Path("spec.doc")) is SourceFormat.WORD_LEGACY
    assert is_supported(SourceFormat.WORD_LEGACY) is False
    # .docx 不受影響:它有完整的前處理路徑。
    assert is_supported(SourceFormat.WORD) is True
