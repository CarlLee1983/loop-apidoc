from __future__ import annotations

from pathlib import Path

from loop_apidoc.manifest.formats import (
    detect_format,
    is_supported,
    unsupported_remedy,
)
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


def test_spreadsheets_are_detected_but_not_supported():
    """試算表與 `.doc` 同一個處置:認得出、拒絕、講得出下一步。

    落到 UNKNOWN 的最終結果一樣是拒絕,差別在拒絕時說不說得出下一步。
    不建轉檔器的理由記在 ADR 0012。
    """
    assert detect_format(Path("codes.xlsx")) is SourceFormat.SPREADSHEET
    assert detect_format(Path("codes.xls")) is SourceFormat.SPREADSHEET
    assert detect_format(Path("codes.XLSX")) is SourceFormat.SPREADSHEET
    assert is_supported(SourceFormat.SPREADSHEET) is False


def test_each_unsupported_format_names_its_own_next_step():
    """remedy 要具名到格式。「轉成受支援的格式」對拿著 .xlsx 的人等於沒說。"""
    spreadsheet = unsupported_remedy(SourceFormat.SPREADSHEET)
    assert "Markdown" in spreadsheet.zh
    assert "markdown" in spreadsheet.en.lower()

    legacy_word = unsupported_remedy(SourceFormat.WORD_LEGACY)
    assert ".docx" in legacy_word.zh
    assert ".docx" in legacy_word.en

    # 未知副檔名沒有可具名的下一步,維持通則。
    unknown = unsupported_remedy(SourceFormat.UNKNOWN)
    assert unknown.zh and unknown.en


def test_the_spreadsheet_remedy_does_not_promise_csv():
    """CSV 不在受支援副檔名裡,叫人另存 CSV 等於把他送進同一個 unsupported。"""
    assert detect_format(Path("codes.csv")) is SourceFormat.UNKNOWN
    remedy = unsupported_remedy(SourceFormat.SPREADSHEET)
    assert "CSV" not in remedy.zh.upper()
    assert "CSV" not in remedy.en.upper()
