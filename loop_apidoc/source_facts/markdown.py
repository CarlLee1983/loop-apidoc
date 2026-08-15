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

from loop_apidoc.domain.evidence import normalize_excerpt
from loop_apidoc.source_facts.models import (
    EndpointFact,
    ErrorCodeFact,
    PayloadFenceFact,
    SourceFacts,
    TableCellFact,
    TableFact,
)

_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_SETEXT = re.compile(r"^\s{0,3}(=+|-{2,})\s*$")
# info string 可以有多個詞(```json title="Request"、```bash copy)。整行必須
# 收下,否則那道圍籬會被當成內文,區塊裡的表格就會變成假事實。
_FENCE = re.compile(r"^\s{0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
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
# 錯誤碼表的表頭詞彙。命中的那一欄才是碼欄——這與 URL corpus 那個在散文裡撈
# 四五位數的 regex 是結構上不同的東西:這裡只取「表頭自稱是錯誤碼」的整格內容。
_ERROR_CODE_HEADER_TOKENS = ("錯誤碼", "錯誤代碼", "回應碼", "error code", "errcode")
# 這些表頭太泛用,單看它無法斷定:`| 代碼 | 幣別 |` 的幣別表(USD、TWD)完全符合
# 碼的形狀。要有章節標題佐證才算數——認錯一張表會生出假事實,而假事實會擋掉
# 正確的擷取,所以模糊時沉默。
_AMBIGUOUS_CODE_HEADER_TOKENS = ("代碼", "狀態碼", "status code", "code")
_ERROR_SECTION_TOKENS = ("錯誤", "例外", "error", "exception")
# 碼的形狀刻意不沿用 _IDENTIFIER——它禁止開頭是數字,而 `1001` 正是最常見的形狀。
# 收下 1001 / E1001 / INVALID_REQUEST / ERR-001 / 40001。
_ERROR_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
_ERROR_CODE_MAX_LENGTH = 32
_REQUIRED_HEADERS = ("required", "mandatory", "必填", "是否必填")
_REQUIRED_TRUE = {"y", "yes", "true", "required", "必填", "是"}
_REQUIRED_FALSE = {"n", "no", "false", "optional", "非必填", "否"}


def scan_markdown(relative_path: str, text: str) -> SourceFacts:
    """掃出這份 Markdown 中每個端點小節的機械事實。"""
    state = _ScanState(relative_path)
    lines = text.splitlines()

    for index, raw in enumerate(lines, start=1):
        fence = _FENCE.match(raw)
        if state.in_fence:
            if fence and state.closes_fence(
                fence.group("marker"), fence.group("info")
            ):
                state.close_fence()
            continue
        if fence:
            state.flush_table()
            state.open_fence(
                fence.group("marker"), _fence_language(fence), lines, index
            )
            continue

        if raw.lstrip().startswith("|"):
            state.table.append((index, raw))
            continue
        state.flush_table()

        heading = _HEADING.match(raw)
        if heading:
            state.open_heading(
                heading.group(2).strip(),
                len(heading.group(1)),
                index,
                raw,
            )
            continue

        if _SETEXT.match(raw) and state.previous.strip():
            # setext 標題的文字在上一行,遇到底線時才知道那是標題。
            state.open_heading(
                state.previous.strip(),
                1 if raw.strip().startswith("=") else 2,
                index,
                state.previous,
            )
            state.previous = raw
            continue

        declared = _declared_endpoint(raw)
        if declared:
            state.declare(declared, index, excerpt=raw)
        state.previous = raw

    state.flush_table()
    state.finish_section(len(lines))
    return SourceFacts(
        relative_path=relative_path,
        endpoints=state.endpoints,
        error_codes=state.error_codes,
    )


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
        self.fence_marker: str | None = None
        self.fence_length = 0
        self.table: list[tuple[int, str]] = []
        self.previous = ""
        # 錯誤碼表不依附端點,所以索引與累積都在來源層級。
        self.error_codes: list[ErrorCodeFact] = []
        self.error_table_index = 0
        # 包住目前位置的標題層級堆疊。錯誤碼表常寫成 `## 錯誤碼` → `### 支付類`
        # → 表格,只看最近一層標題會漏掉整批分組。
        self.heading_stack: list[tuple[int, str]] = []

    @property
    def in_fence(self) -> bool:
        return self.fence_marker is not None

    def open_fence(
        self, marker: str, info: str, lines: list[str], index: int
    ) -> None:
        if self.current is not None:
            if _is_payload_fence(info, lines, index, marker):
                self.current.example_blocks += 1
                self.current.payload_fences += (
                    _payload_fence(info, lines, index, marker),
                )
        self.fence_marker = marker[0]
        self.fence_length = len(marker)
        self.previous = ""

    def closes_fence(self, marker: str, info: str) -> bool:
        return (
            not info.strip()
            and marker[0] == self.fence_marker
            and len(marker) >= self.fence_length
        )

    def close_fence(self) -> None:
        self.fence_marker = None
        self.fence_length = 0
        self.previous = ""

    def flush_table(self) -> None:
        if self.table:
            fact = _absorb_table(self.current, self.table)
            if self.current is not None and fact is not None:
                self.current.tables += (fact,)
            # 端點狀態無關:錯誤碼表通常落在所有端點小節之外。
            codes = _absorb_error_codes(
                self.relative_path,
                self.table,
                self.error_table_index,
                headings=tuple(title for _, title in self.heading_stack),
            )
            if codes:
                self.error_codes.extend(codes)
                self.error_table_index += 1
            self.table = []

    def open_heading(
        self,
        title: str,
        level: int,
        index: int,
        excerpt: str,
    ) -> None:
        self.last_heading = title
        self.last_heading_level = level
        while self.heading_stack and self.heading_stack[-1][0] >= level:
            self.heading_stack.pop()
        self.heading_stack.append((level, title))
        declared = _declared_endpoint(title)
        if declared:
            self.declare(
                declared,
                index,
                level=level,
                heading=title,
                excerpt=excerpt,
            )
            return
        if self.current is not None and level <= self.declaring_level:
            self.finish_section(index - 1)
            self.current = None

    def declare(
        self,
        declared: tuple[str, str],
        line: int,
        *,
        level: int | None = None,
        heading: str | None = None,
        excerpt: str,
    ) -> None:
        if self.current is not None:
            self.finish_section(line - 1)
        method, path = declared
        self.current = EndpointFact(
            relative_path=self.relative_path,
            heading=heading if heading is not None else self.last_heading,
            method=method,
            path=path,
            line=line,
            declaration_start_line=line,
            declaration_end_line=line,
            declaration_excerpt=normalize_excerpt(excerpt),
            section_start_line=line,
        )
        self.endpoints.append(self.current)
        # 由獨立行宣告的端點,其「所在層級」是包住它的那個標題——
        # 少了這個,後續的同級標題就無法結束這一節。
        self.declaring_level = level if level is not None else self.last_heading_level

    def finish_section(self, line: int) -> None:
        if self.current is not None and self.current.section_end_line is None:
            self.current.section_end_line = max(
                self.current.section_start_line or line,
                line,
            )


def _is_payload_fence(
    info: str, lines: list[str], index: int, opening_marker: str
) -> bool:
    if info.strip().lower() in _PAYLOAD_INFO:
        return True
    for line in lines[index:]:
        stripped = line.strip()
        if not stripped:
            continue
        fence = _FENCE.match(line)
        if fence and _matches_closing_fence(opening_marker, fence):
            return False
        return stripped[0] in "{[<"
    return False


def _payload_fence(
    info: str,
    lines: list[str],
    opening_line: int,
    opening_marker: str,
) -> PayloadFenceFact:
    content: list[str] = []
    closing_line = opening_line
    for line_number, line in enumerate(
        lines[opening_line:],
        start=opening_line + 1,
    ):
        fence = _FENCE.match(line)
        if fence and _matches_closing_fence(opening_marker, fence):
            closing_line = line_number
            break
        content.append(line)
        closing_line = line_number
    return PayloadFenceFact(
        info=info.strip().lower(),
        start_line=opening_line,
        end_line=closing_line,
        normalized_excerpt=normalize_excerpt("\n".join(content)),
    )


def _matches_closing_fence(opening_marker: str, fence: re.Match[str]) -> bool:
    marker = fence.group("marker")
    return (
        not fence.group("info").strip()
        and marker[0] == opening_marker[0]
        and len(marker) >= len(opening_marker)
    )


def _fence_language(fence: re.Match[str]) -> str:
    """只有 info string 的第一個詞是語言;其餘是 title/highlight 等裝飾。"""
    info = fence.group("info").strip().strip("`").strip()
    return info.split()[0] if info else ""


def _declared_endpoint(line: str) -> tuple[str, str] | None:
    """從一行文字辨識 `METHOD /path`,允許 backtick / 粗體 / 清單符號包裝。"""
    cleaned = line.strip().lstrip("-*+ \t").strip("`* \t")
    match = _ENDPOINT.match(cleaned)
    if not match:
        return None
    method = cleaned.split(maxsplit=1)[0].upper()
    path = match.group("path").strip("`,。;;、)】")
    return method, path


def _absorb_table(
    current: EndpointFact | None,
    rows: list[tuple[int, str]],
) -> TableFact | None:
    """把一張 GFM 表格的「名稱欄」併入目前端點的參數名清單。"""
    if current is None:
        return None
    header = _table_header(rows)
    if header is None:
        return None
    if not _is_name_header(header[0]):
        return None
    if len(header) > 1 and _is_constant_header(header[1]):
        return None

    body = [
        (line, cells)
        for line, row in rows[2:]
        if (cells := _cells(row))
    ]
    column = _name_column(header, [cells for _, cells in body])
    fact_rows: list[tuple[TableCellFact, ...]] = []
    table_index = len(current.tables)
    clean_headers = tuple(normalize_excerpt(_field_name(cell)) for cell in header)
    for row_index, (line, cells) in enumerate(body):
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
        cell_facts: list[TableCellFact] = []
        for column_index, cell in enumerate(cells):
            column_name = (
                clean_headers[column_index]
                if column_index < len(clean_headers)
                else str(column_index)
            )
            excerpt = normalize_excerpt(cell.strip().strip("`*_ "))
            semantic_value: object = excerpt
            if column_index == column:
                excerpt = name
                semantic_value = name
            elif _is_required_header(column_name):
                semantic_value = _requiredness_value(excerpt)
            cell_facts.append(
                TableCellFact(
                    locator={
                        "table_index": table_index,
                        "row_index": row_index,
                        "column_index": column_index,
                        "column_name": column_name,
                    },
                    line=line,
                    normalized_excerpt=excerpt,
                    semantic_value=semantic_value,
                )
            )
        fact_rows.append(tuple(cell_facts))
    return TableFact(
        table_index=table_index,
        start_line=rows[0][0],
        end_line=rows[-1][0],
        headers=clean_headers,
        rows=tuple(fact_rows),
    )


def _absorb_error_codes(
    relative_path: str,
    rows: list[tuple[int, str]],
    table_index: int,
    *,
    headings: tuple[str, ...],
) -> list[ErrorCodeFact]:
    """把一張錯誤碼表格攤成記載錯誤碼下界的成員。

    整表成立或整表作廢,不做逐列挑選:漏掉一列會安靜地把下界調低,而下界調低
    正是這道檢查要防的東西;整表沉默則等同今天的行為,是安全的那一邊。
    """
    header = _table_header(rows)
    # 只有碼、沒有意義欄的表多半不是錯誤碼表。
    if header is None or len(header) < 2:
        return []
    column = _error_code_column(header, headings)
    if column is None:
        return []

    clean_headers = [normalize_excerpt(_field_name(cell)) for cell in header]
    facts: list[ErrorCodeFact] = []
    for row_index, (line, row) in enumerate(rows[2:]):
        cells = _cells(row)
        if not cells or column >= len(cells):
            return []
        code = normalize_excerpt(cells[column].strip().strip("`*_ "))
        # 分組標題列(「支付類」)其餘欄位全空,且碼欄本身不是碼的形狀。兩個條件
        # 都要:`| 1001 | |` 也是其餘欄位全空,但它是說明留白的真資料列,把它
        # 當標題跳過會安靜地把下界調低,正好是這道檢查要防的事。
        others_blank = len(cells) > 1 and not any(
            cell.strip() for index, cell in enumerate(cells) if index != column
        )
        if others_blank and not _is_error_code(code):
            continue
        if not _is_error_code(code):
            return []
        facts.append(
            ErrorCodeFact(
                relative_path=relative_path,
                code=code,
                line=line,
                table_index=table_index,
                row_index=row_index,
                column_index=column,
                column_name=clean_headers[column],
                normalized_excerpt=normalize_excerpt(row.strip()),
            )
        )
    return facts


def _table_header(rows: list[tuple[int, str]]) -> list[str] | None:
    """GFM 表格的表頭列;湊不齊表頭 + 分隔列 + 至少一列內文就不算表格。"""
    if len(rows) < 3:
        return None
    header = _cells(rows[0][1])
    if not header or not _TABLE_SEPARATOR.match(rows[1][1]):
        return None
    return header


def _error_code_column(header: list[str], headings: tuple[str, ...]) -> int | None:
    """哪一欄是碼欄——明確的表頭直接算數,模糊的表頭要有錯誤章節佐證。

    完全相符優先於包含:`| 錯誤碼分類 | 錯誤碼 | 說明 |` 的碼欄是第二欄,
    照「第一個命中」會挑到分類欄,整張表就跟著作廢。
    模糊詞彙只認完全相符——`國家代碼`、`幣別代碼` 都包含「代碼」,放寬成包含
    會把國別表、幣別表整批認成錯誤碼。
    """
    lowered = [cell.strip().strip("`*_ ").lower() for cell in header]
    # 不走 _field_name:它會從第一個空白截斷(那是為參數名後的註記設計的),
    # 「Error Code」會被砍成「Error」。
    for index, cell in enumerate(lowered):
        if cell in _ERROR_CODE_HEADER_TOKENS:
            return index
    for index, cell in enumerate(lowered):
        if any(token in cell for token in _ERROR_CODE_HEADER_TOKENS):
            return index
    if not _is_error_section(headings):
        return None
    for index, cell in enumerate(lowered):
        if cell in _AMBIGUOUS_CODE_HEADER_TOKENS:
            return index
    return None


def _is_error_section(headings: tuple[str, ...]) -> bool:
    """包住這張表的任何一層標題是錯誤章節就算數。

    `## 錯誤碼` → `### 支付類` → 表格,是主流的分組寫法;只看最近的一層標題
    會漏掉它們全部。
    """
    return any(
        token in heading.lower()
        for heading in headings
        for token in _ERROR_SECTION_TOKENS
    )


def _is_error_code(value: str) -> bool:
    return bool(value) and len(value) <= _ERROR_CODE_MAX_LENGTH and bool(
        _ERROR_CODE.match(value)
    )


def _is_required_header(value: str) -> bool:
    lowered = value.strip().lower()
    return any(token in lowered for token in _REQUIRED_HEADERS)


def _requiredness_value(value: str) -> bool | str:
    normalized = value.strip()
    lowered = normalized.lower()
    if lowered in _REQUIRED_TRUE:
        return True
    if lowered in _REQUIRED_FALSE:
        return False
    return normalized


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
