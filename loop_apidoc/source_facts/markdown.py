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
_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_ENDPOINT = re.compile(
    rf"^(?:{'|'.join(_HTTP_METHODS)})\s+(?P<path>/\S*)",
)
_TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")

# 巢狀欄位的排版裝飾:縮排實體與樹狀符號。照字面收下,閘門就會要求一個
# 名叫 "&nbsp;&nbsp;user.id" 的欄位——沒有任何正確擷取能滿足它。
_ROW_DECORATION = re.compile(r"^(?:&nbsp;|&emsp;|&ensp;|[\s│|├└─↳→\-*+·•])+")

# 只有標頭第一欄看起來像「名稱欄」時,整張表才算參數表。
# 匯率表、狀態碼對照表都不該被誤認成參數。
_NAME_HEADER_TOKENS = (
    "name", "field", "parameter", "param", "attribute", "property", "key",
    "參數", "欄位", "名稱", "屬性", "變數", "參數名", "键", "键名",
)


def scan_markdown(relative_path: str, text: str) -> SourceFacts:
    """掃出這份 Markdown 中每個端點小節的機械事實。"""
    endpoints: list[EndpointFact] = []
    current: EndpointFact | None = None
    last_heading: str | None = None
    in_fence = False
    table: list[str] = []

    lines = text.splitlines()
    for index, raw in enumerate(lines, start=1):
        if _FENCE.match(raw):
            if not in_fence and current is not None:
                current.example_blocks += 1
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        if raw.lstrip().startswith("|"):
            table.append(raw)
            continue
        if table:
            _absorb_table(current, table)
            table = []

        heading = _HEADING.match(raw)
        if heading:
            title = heading.group(2).strip()
            declared = _declared_endpoint(title)
            last_heading = title
            if declared:
                current = _fact(relative_path, title, declared, index)
                endpoints.append(current)
            else:
                current = None
            continue

        declared = _declared_endpoint(raw)
        if declared:
            current = _fact(relative_path, last_heading, declared, index)
            endpoints.append(current)

    if table:
        _absorb_table(current, table)

    return SourceFacts(relative_path=relative_path, endpoints=endpoints)


def _fact(
    relative_path: str, heading: str | None, declared: tuple[str, str], line: int
) -> EndpointFact:
    method, path = declared
    return EndpointFact(
        relative_path=relative_path,
        heading=heading,
        method=method,
        path=path,
        line=line,
    )


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
    """把一張 GFM 表格的第一欄併入目前端點的參數名清單。"""
    if current is None or len(rows) < 3:
        return
    header = _cells(rows[0])
    if not header or not _TABLE_SEPARATOR.match(rows[1]):
        return
    if not _is_name_header(header[0]):
        return
    for row in rows[2:]:
        cells = _cells(row)
        if not cells:
            continue
        # 其餘欄位全空的列是分組標題(「Header」「Query」),不是欄位。
        # 單欄表沒有「其餘欄位」可判,不套這條規則。
        if len(cells) > 1 and not any(cell.strip() for cell in cells[1:]):
            continue
        name = _field_name(cells[0])
        if name and name not in current.parameter_names:
            current.parameter_names.append(name)


def _field_name(cell: str) -> str:
    return _ROW_DECORATION.sub("", cell.strip()).strip("`*_ ")


def _cells(row: str) -> list[str]:
    stripped = row.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_name_header(cell: str) -> bool:
    lowered = cell.strip().lower()
    return any(token in lowered for token in _NAME_HEADER_TOKENS)
