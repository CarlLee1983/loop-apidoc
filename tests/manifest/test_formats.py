from __future__ import annotations

from pathlib import Path

from loop_apidoc.manifest.formats import (
    _UNSUPPORTED,
    _UNSUPPORTED_REMEDIES,
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
    assert detect_format(Path("notes.bin")) is SourceFormat.UNKNOWN


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
    remedy = unsupported_remedy(SourceFormat.WORD_LEGACY)
    assert ".docx" in remedy.zh
    assert ".docx" in remedy.en


def test_spreadsheets_are_detected_but_not_supported():
    """試算表與 `.doc` 同一個處置:認得出、拒絕、講得出下一步。

    落到 UNKNOWN 的最終結果一樣是拒絕,差別在拒絕時說不說得出下一步。
    不建轉檔器的理由記在 ADR 0012。
    """
    assert detect_format(Path("codes.xlsx")) is SourceFormat.SPREADSHEET
    assert detect_format(Path("codes.xls")) is SourceFormat.SPREADSHEET
    assert detect_format(Path("codes.XLSX")) is SourceFormat.SPREADSHEET
    assert is_supported(SourceFormat.SPREADSHEET) is False
    remedy = unsupported_remedy(SourceFormat.SPREADSHEET)
    assert "Markdown" in remedy.zh
    assert "markdown" in remedy.en.lower()


def test_every_unsupported_format_except_unknown_has_a_named_remedy():
    """忘記登記 remedy 的格式會靜靜落到通則,而通則式的斷言測不出這件事——
    所以直接斷言「有沒有登記」本身,而不是手寫一份格式清單去核對(那份清單
    本身就會忘記更新)。`UNKNOWN` 沒有可具名的下一步,維持通則,不在此列。
    """
    named = [f for f in _UNSUPPORTED if f is not SourceFormat.UNKNOWN]
    assert named
    for source_format in named:
        assert source_format in _UNSUPPORTED_REMEDIES, source_format

    unknown = unsupported_remedy(SourceFormat.UNKNOWN)
    assert unknown.zh and unknown.en


def test_the_spreadsheet_remedy_does_not_promise_csv():
    """叫人另存 CSV 等於把他送進同一個 unsupported——.csv 自己就落在這裡。"""
    remedy = unsupported_remedy(SourceFormat.SPREADSHEET)
    assert ".csv" not in remedy.zh.lower()
    assert ".csv" not in remedy.en.lower()


def test_plain_text_is_detected_but_not_supported():
    """`.txt` 與 `.doc`／試算表同一個處置:認得出、拒絕、講得出下一步。

    `.txt` 的內容通常就是可讀文字,下一步不是通則裡的四選一,而是「改副檔名」。
    """
    assert detect_format(Path("notes.txt")) is SourceFormat.PLAIN_TEXT
    assert is_supported(SourceFormat.PLAIN_TEXT) is False
    remedy = unsupported_remedy(SourceFormat.PLAIN_TEXT)
    assert ".md" in remedy.zh
    assert ".md" in remedy.en


def test_csv_is_detected_but_not_supported():
    """`.csv` 落進自己的具名格式,不再是通則,也不建議另存 CSV(#98 的決定)。"""
    assert detect_format(Path("codes.csv")) is SourceFormat.CSV
    assert detect_format(Path("codes.CSV")) is SourceFormat.CSV
    assert is_supported(SourceFormat.CSV) is False
    remedy = unsupported_remedy(SourceFormat.CSV)
    assert "Markdown" in remedy.zh
    assert "markdown" in remedy.en.lower()
    # 不建議另存 CSV:那會把 operator 送回這個 unsupported。「.csv」不能出現
    # 在建議的動作裡——只比對片語會放過「re-save it as a CSV file」這類措辭。
    assert ".csv" not in remedy.zh.lower()
    assert ".csv" not in remedy.en.lower()
    # remedy 要以 CSV 本身為主詞,不是誤指到試算表那一筆——兩者都提
    # Markdown,單靠這個詞分辨不出用錯了哪一筆。
    spreadsheet_remedy = unsupported_remedy(SourceFormat.SPREADSHEET)
    assert remedy.zh != spreadsheet_remedy.zh
    assert remedy.en != spreadsheet_remedy.en
    assert "CSV" in remedy.zh
    assert "csv" in remedy.en.lower()
    assert "試算表" not in remedy.zh
    assert "spreadsheet" not in remedy.en.lower()
