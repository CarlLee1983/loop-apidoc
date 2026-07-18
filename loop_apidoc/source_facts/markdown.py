"""Markdown 來源的機械掃描:標題 / 端點宣告 / 參數表 / 範例區塊。

純函式,不碰檔案系統。刻意保守——寧可漏掉一個事實,也不要生出一個
來源沒寫的事實,因為下游的完整性閘門會把事實當成「必須被擷取」的證據,
一個假事實就會擋掉一份正確的擷取。

**已知範圍限制**:只有結構良好的 Markdown(標題、GFM 表格、圍籬區塊)
掃得出事實。把 HTML 壓平成長單行的來源會掃出零個事實,閘門對它等同無效。
這是接受的取捨,不是待修的 bug——要涵蓋那類來源,得先在取源階段把結構
還原(見 `html_snapshot.py`),而不是在這裡猜。
"""

from __future__ import annotations

import re

from loop_apidoc.source_facts.models import EndpointFact, SourceFacts

_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_SETEXT = re.compile(r"^\s{0,3}(=+|-{2,})\s*$")
_FENCE = re.compile(r"^\s{0,3}(?:```|~~~)\s*(?P<info>[^\s`]*)")
_ENDPOINT = re.compile(rf"^(?:{'|'.join(_HTTP_METHODS)})\s+(?P<path>/\S*)")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")

_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_LINE_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
# 巢狀欄位的排版裝飾:縮排實體與樹狀符號。照字面收下,閘門就會要求一個
# 名叫 "&nbsp;&nbsp;user.id" 的欄位——沒有任何正確擷取能滿足它。
_ROW_DECORATION = re.compile(r"^(?:&nbsp;|&emsp;|&ensp;|[\s│|├└─↳→\-*+·•])+")
# 註記常直接黏在欄位名後面(`username(必填)`、`X-Token (required)`)。
_ANNOTATION = re.compile(r"[\s(（\[【].*$")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")

# 只有標頭第一欄看起來像「名稱欄」時,整張表才算參數表。
# 匯率表、狀態碼對照表都不該被誤認成參數。
_NAME_HEADER_TOKENS = (
    "name", "field", "parameter", "param", "attribute", "property", "key",
    "參數", "欄位", "名稱", "屬性", "變數", "參數名", "键", "键名",
)
# 第二欄是「值」的表是常數對照表(Content-Type: application/json),
# 不是參數表——正確的擷取會把它模型成 media type 而非參數。
_CONSTANT_HEADER_TOKENS = ("value", "值", "內容", "example value")
# 內容協商標頭由 media type 承載,不是參數。
_NEGOTIATION_HEADERS = {"content-type", "accept", "content-length", "accept-encoding"}

# 只有裝得下 payload 的圍籬才算範例。簽章章節滿是虛擬碼圍籬,
# 把它們當範例會逼出一個來源根本沒有的 examples。
_PAYLOAD_INFO = {
    "json", "xml", "http", "curl", "yaml", "yml", "javascript", "js",
    "response", "request", "jsonc", "html",
}


def scan_markdown(relative_path: str, text: str) -> SourceFacts:
    """掃出這份 Markdown 中每個端點小節的機械事實。"""
    state = _ScanState(relative_path)
    lines = text.splitlines()

    for index, raw in enumerate(lines, start=1):
        fence = _FENCE.match(raw)
        if fence:
            state.flush_table()
            state.toggle_fence(fence.group("info"), lines, index)
            continue
        if state.in_fence:
            continue

        if raw.lstrip().startswith("|"):
            state.table.append(raw)
            continue
        state.flush_table()

        heading = _HEADING.match(raw)
        if heading:
            state.open_heading(heading.group(2).strip(), len(heading.group(1)), index)
            continue

        if _SETEXT.match(raw) and state.previous.strip():
            # setext 標題的文字在上一行,遇到底線時才知道那是標題。
            state.open_heading(
                state.previous.strip(), 1 if raw.strip().startswith("=") else 2, index)
            state.previous = raw
            continue

        declared = _declared_endpoint(raw)
        if declared:
            state.declare(declared, index)
        state.previous = raw

    state.flush_table()
    return SourceFacts(relative_path=relative_path, endpoints=state.endpoints)


class _ScanState:
    """掃描過程中的可變狀態。刻意集中在一處,免得散落成隱性耦合。"""

    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.endpoints: list[EndpointFact] = []
        self.current: EndpointFact | None = None
        self.last_heading: str | None = None
        self.last_heading_level = 0
        # 宣告目前端點的那個標題層級。更深的子標題(「### 請求參數」)是同一個
        # 端點的內文,不是換段;把它當換段,參數表就不會歸屬任何端點。
        self.declaring_level = 0
        self.in_fence = False
        self.table: list[str] = []
        self.previous = ""

    def toggle_fence(self, info: str, lines: list[str], index: int) -> None:
        if not self.in_fence and self.current is not None:
            if _is_payload_fence(info, lines, index):
                self.current.example_blocks += 1
        self.in_fence = not self.in_fence
        self.previous = ""

    def flush_table(self) -> None:
        if self.table:
            _absorb_table(self.current, self.table)
            self.table = []

    def open_heading(self, title: str, level: int, index: int) -> None:
        self.last_heading = title
        self.last_heading_level = level
        declared = _declared_endpoint(title)
        if declared:
            self.declare(declared, index, level=level, heading=title)
            return
        if self.current is not None and level <= self.declaring_level:
            self.current = None

    def declare(
        self,
        declared: tuple[str, str],
        line: int,
        *,
        level: int | None = None,
        heading: str | None = None,
    ) -> None:
        method, path = declared
        self.current = EndpointFact(
            relative_path=self.relative_path,
            heading=heading if heading is not None else self.last_heading,
            method=method,
            path=path,
            line=line,
        )
        self.endpoints.append(self.current)
        # 由獨立行宣告的端點,其「所在層級」是包住它的那個標題——
        # 少了這個,後續的同級標題就無法結束這一節。
        self.declaring_level = level if level is not None else self.last_heading_level


def _is_payload_fence(info: str, lines: list[str], index: int) -> bool:
    if info.strip().lower() in _PAYLOAD_INFO:
        return True
    for line in lines[index:]:
        stripped = line.strip()
        if not stripped:
            continue
        if _FENCE.match(line):
            return False
        return stripped[0] in "{[<"
    return False


def _declared_endpoint(line: str) -> tuple[str, str] | None:
    """從一行文字辨識 `METHOD /path`,允許 backtick / 粗體 / 清單符號包裝。"""
    cleaned = line.strip().lstrip("-*+ \t").strip("`* \t")
    match = _ENDPOINT.match(cleaned)
    if not match:
        return None
    method = cleaned.split(maxsplit=1)[0].upper()
    path = match.group("path").strip("`,。;;、)】")
    return method, path


def _absorb_table(current: EndpointFact | None, rows: list[str]) -> None:
    """把一張 GFM 表格的「名稱欄」併入目前端點的參數名清單。"""
    if current is None or len(rows) < 3:
        return
    header = _cells(rows[0])
    if not header or not _TABLE_SEPARATOR.match(rows[1]):
        return
    if not _is_name_header(header[0]):
        return
    if len(header) > 1 and _is_constant_header(header[1]):
        return

    body = [cells for row in rows[2:] if (cells := _cells(row))]
    column = _name_column(header, body)
    for cells in body:
        # 其餘欄位全空的列是分組標題(「Header」「Query」),不是欄位。
        # 單欄表沒有「其餘欄位」可判,不套這條規則。
        if len(cells) > 1 and not any(cell.strip() for cell in cells[1:]):
            continue
        if column >= len(cells):
            continue
        name = _field_name(cells[column])
        if not name or name.lower() in _NEGOTIATION_HEADERS:
            continue
        if name not in current.parameter_names:
            current.parameter_names.append(name)


def _name_column(header: list[str], body: list[list[str]]) -> int:
    """挑出真正承載欄位名的那一欄。

    中文文件常把第一欄寫成人看的標籤、第二欄才是實際的 wire 欄位名
    (`| 商店代號 | MerchantID |`)。照第一欄要求,正確的擷取永遠過不了。
    改欄的條件很緊:第一欄整欄都不像識別字,而候選欄整欄都像 **且它的表頭
    本身也是名稱欄**。少了表頭那道條件,`| 商店代號 | string |` 會把「型態」
    欄當成欄位名。沒有合格候選就留在第一欄——CJK 鍵名本身也可能就是真的鍵。
    """
    if not body or _column_is_identifier(body, 0):
        return 0
    width = max(len(cells) for cells in body)
    for index in range(1, min(width, len(header))):
        if _is_name_header(header[index]) and _column_is_identifier(body, index):
            return index
    return 0


def _column_is_identifier(body: list[list[str]], index: int) -> bool:
    values = [
        _field_name(cells[index])
        for cells in body
        if index < len(cells) and _field_name(cells[index])
    ]
    return bool(values) and all(_IDENTIFIER.match(value) for value in values)


def _field_name(cell: str) -> str:
    name = _LINE_BREAK.split(cell.strip(), maxsplit=1)[0]
    name = _MD_LINK.sub(r"\1", name)
    name = _ROW_DECORATION.sub("", name)
    return _ANNOTATION.sub("", name.strip()).strip("`*_ ")


def _cells(row: str) -> list[str]:
    stripped = row.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_name_header(cell: str) -> bool:
    lowered = _field_name(cell).lower()
    return any(token in lowered for token in _NAME_HEADER_TOKENS)


def _is_constant_header(cell: str) -> bool:
    lowered = cell.strip().lower()
    return any(token == lowered for token in _CONSTANT_HEADER_TOKENS)
