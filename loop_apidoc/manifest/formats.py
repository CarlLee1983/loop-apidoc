from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

from loop_apidoc.manifest.models import SourceFormat

_EXTENSION_FORMATS: dict[str, SourceFormat] = {
    ".pdf": SourceFormat.PDF,
    ".md": SourceFormat.MARKDOWN,
    ".markdown": SourceFormat.MARKDOWN,
    ".docx": SourceFormat.WORD,
    ".doc": SourceFormat.WORD_LEGACY,
    ".xlsx": SourceFormat.SPREADSHEET,
    ".xls": SourceFormat.SPREADSHEET,
    ".json": SourceFormat.OPENAPI_JSON,
    ".yaml": SourceFormat.OPENAPI_YAML,
    ".yml": SourceFormat.OPENAPI_YAML,
    ".html": SourceFormat.HTML,
    ".htm": SourceFormat.HTML,
}


def detect_format(path: Path) -> SourceFormat:
    return _EXTENSION_FORMATS.get(path.suffix.lower(), SourceFormat.UNKNOWN)


#: 認得出格式不等於讀得動。舊版二進位 Word 與試算表都沒有前處理路徑
#: (`preprocess` 只轉 `.pdf`/`.docx`),掃描器也讀不了它們,所以標成 supported 是
#: 一句不成立的宣稱——而 manifest 是 operator 第一個看到的東西。
_UNSUPPORTED = (
    SourceFormat.UNKNOWN,
    SourceFormat.WORD_LEGACY,
    SourceFormat.SPREADSHEET,
)


def is_supported(source_format: SourceFormat) -> bool:
    return source_format not in _UNSUPPORTED


@dataclass(frozen=True)
class UnsupportedRemedy:
    """一個被拒絕的格式,下一步該做什麼。

    兩種語言各留一份而不是共用一句:`validate/` 的發現寫中文(#84、#90 的語言
    一致性決定),`preparation/` 與 `score/` 自己產的發現寫英文。這不是「分數
    一定是英文」——`score/evaluate.py` 會把 validate 的發現連同中文 remedy 原封
    轉傳,所以同一份分數報告裡兩種語言本來就並存。統一它們是另一個決定,
    這裡只確保共用的是判斷本身:哪個格式對應哪個下一步只寫在這裡一次。
    """

    zh: str
    en: str


#: 拒絕時說不說得出下一步,決定了 operator 是被擋住還是被卡住。
#: 不為這些格式建轉檔器是刻意的決定,不是還沒做——見 ADR 0012。
_GENERIC_REMEDY = UnsupportedRemedy(
    zh="轉為受支援格式（PDF／Markdown／.docx／OpenAPI）放回 sources/ 後重跑前處理，或確認可略過",
    en=(
        "convert it to a supported format — PDF, Markdown, .docx or OpenAPI — into "
        "sources/ and preprocess again, or drop it"
    ),
)
_UNSUPPORTED_REMEDIES: dict[SourceFormat, UnsupportedRemedy] = {
    # 措辭要在四個現場都成立:preparation／coverage／分數三份報告,以及
    # `preprocess` 的 passthrough 那一行。所以結尾說「放回 sources/ 後重跑前處理」——
    # 強制順序是 preprocess → manifest → risk,從前處理重來在四處都是對的,
    # 而「remove it from the run」在 run 還不存在的那一行是錯的。
    SourceFormat.WORD_LEGACY: UnsupportedRemedy(
        zh="舊版二進位 Word 這條管線讀不動，請另存為 .docx 或 PDF 放回 sources/ 後重跑前處理",
        en=(
            "legacy binary Word is not readable by this pipeline; re-save it as "
            ".docx or PDF into sources/ and preprocess again"
        ),
    ),
    # 刻意不說 CSV:`.csv` 不在受支援副檔名裡,叫人另存 CSV 會把他送回同一個
    # unsupported,而且來源事實只從 Markdown 讀得出來。
    SourceFormat.SPREADSHEET: UnsupportedRemedy(
        zh=(
            "試算表這條管線讀不動，"
            "請把需要的工作表另存為 Markdown 表格放進 sources/ 後重跑前處理"
        ),
        en=(
            "spreadsheets are not readable by this pipeline; export the sheet you "
            "need as a Markdown table into sources/ and preprocess again"
        ),
    ),
}


def unsupported_remedy(source_format: SourceFormat) -> UnsupportedRemedy:
    """這個格式的下一步。未知副檔名沒有可具名的下一步,回通則。"""
    return _UNSUPPORTED_REMEDIES.get(source_format, _GENERIC_REMEDY)


def guess_mime_type(path: Path) -> str | None:
    mime, _ = mimetypes.guess_type(path.name)
    return mime
