from __future__ import annotations

import re
from collections.abc import Iterator


FORBIDDEN_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "set_cookie",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "access_token",
        "refresh_token",
        "token",
        "api_key",
        "apikey",
        "x_api_key",
        "credential",
        "credentials",
        "email",
        "phone",
        "phone_number",
        "national_id",
        "ssn",
        "social_security_number",
        "passport",
        "passport_number",
        "credit_card",
        "card_number",
        "payment_card_number",
        "pan",
        "bank_account",
        "iban",
        "date_of_birth",
        "dob",
    }
)
_FORBIDDEN_COMPACT_KEYS = frozenset(key.replace("_", "") for key in FORBIDDEN_KEYS)
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_KEY_SEPARATOR = re.compile(r"[^A-Za-z0-9]+")
#: 自證性密鑰材料:結構本身就是證據,不需要判斷內容是真是假。PEM 私鑰
#: 區塊與 JWT 幾乎不可能是文件裡的示意寫法,所以來源風險閘把它當 blocker。
#: A JWT, as a body with no anchors, so one definition serves both the
#: document scan (`SECRET_MATERIAL`, word-bounded) and the URL path-segment
#: check in `url_safety` (anchored). `eyJ`, not `ey`: the first segment decodes
#: from `{"`, and `ey` alone matches ordinary words like `eyebrow.guide.md`.
JWT_BODY = r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
SECRET_MATERIAL = re.compile(
    r"(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    rf"\b{JWT_BODY}\b)"
)
#: 憑證引用:`Authorization: Bearer <TOKEN>`、`API-Key: YOUR_API_KEY` 這類。
#: 在治理酬載裡它們是真值,在來源文件裡幾乎總是佔位符 —— 同一組樣式,兩種
#: 語境,語意相反。分開之後,治理端維持原行為,來源風險閘只給 warning:
#: 值是真是假無法從文字確定,而猜錯的兩個方向都有代價。
CREDENTIAL_REFERENCE = re.compile(
    r"(?i)(?:\bbearer\s+\S+|\bbasic\s+\S+|"
    r"\b(?:password|passwd|secret|client[_-]?secret|access[_-]?token|"
    r"refresh[_-]?token|api[_-]?key|authorization|cookie)\s*[:=]\s*\S+)"
)
#: 聯絡類 PII。低熵、常態出現在正當的供應商文件裡(技術窗口信箱),
#: 所以它單獨成一個樣式而不與密鑰材料混編。
#: local part 依 RFC 5321 上限 64;網域寫成有界的 label 結構而非
#: `[^\s@]+\.[^\s@]+`。後者在整份文件上是二次時間 —— 每個 `\b` 起點都會
#: 吞到底再回溯,一段 184 KB 的 minified CSS 要 52 秒,5 MiB 來源足以讓
#: 這個前置閘停擺。治理端只掃單一 JSON 字串值,所以前移到整份文件才暴露。
CONTACT_PII = re.compile(
    r"(?i)\b[^\s@]{1,64}@"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.){1,8}[a-z]{2,24}\b"
)
#: 身分證字號／護照／社會安全碼／電話。與 `CONTACT_PII` 同級 —— 低熵,
#: 洩漏是隱私問題而非可被拿去打 API 的憑證。
PII_VALUE = re.compile(
    r"(?i)(?:\b[A-Z][12]\d{8}\b|"
    r"(?<!\d)\d{3}[-.\s]\d{2}[-.\s]\d{4}(?!\d)|"
    r"\b(?:passport(?:\s+(?:number|no\.?))?|ssn|social[ -]?security(?:\s+number)?)"
    r"\s*[:#=\-]?\s*[A-Z0-9-]{6,20}\b|"
    r"(?<!\d)(?:\+886[-.\s]?|0)9\d{2}[-.\s]?\d{3}[-.\s]?\d{3}(?!\d)|"
    r"(?<!\d)(?:\+886[-.\s]?|0)\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)|"
    r"(?<!\w)\+\d(?:[-.\s]?\d){7,14}(?!\d))"
)
#: 卡號候選樣式。單獨使用會誤報訂單／商店編號 —— 只能經由
#: `iter_payment_card_numbers` 使用,它才會做 Luhn 檢查與候選內部切窗。
#: 分隔符只排除換行,不排除其他 Unicode 空白 —— 卡號不會跨行,而允許跨行
#: 會把相鄰兩行的訂單編號接成長度合格的候選,再由 Luhn 隨機放行約十分之一。
#: 用 `[-. \t]` 一併排掉 NBSP 與全形空格則是另一個錯誤方向:從 PDF 貼出的
#: 付款範例帶 U+00A0、zh-TW 文件帶 U+3000,那會讓真卡號通過治理閘。
PAYMENT_CARD_CANDIDATE = re.compile(
    r"(?<!\d)(?:\d(?:[-.]|[^\S\r\n])?){12,18}\d(?!\d)"
)
#: 候選內部的數字群。切窗的切點只能落在群邊界 —— 從一串數字中間切開會
#: 憑空造出卡號,而不是找出寫在來源裡的那一個。
_DIGIT_GROUP = re.compile(r"\d+")
#: 各卡組織公告的測試卡號。它們通過 Luhn,但出現在付款文件裡是必要內容
#: 而非外洩 —— 報它們等於對每一份付款文件產生一整排沒人會處理的警告。
TEST_PAYMENT_CARDS = frozenset(
    {
        "4111111111111111",
        "4012888888881881",
        "4222222222222",
        "4000056655665556",
        "5555555555554444",
        "5105105105105100",
        "5200828282828210",
        "378282246310005",
        "371449635398431",
        "378734493671000",
        "6011111111111117",
        "6011000990139424",
        "3530111333300000",
        "3566002020360505",
        "30569309025904",
        "38520000023237",
    }
)


def find_sensitive_value(value: object, *, path: str = "$") -> tuple[str, str] | None:
    """Return the first forbidden value kind and path in a JSON-compatible tree."""
    if isinstance(value, dict):
        for key, item in value.items():
            if _is_forbidden_key(key):
                return "secret or PII field", f"{path}.{key}"
            finding = find_sensitive_value(item, path=f"{path}.{key}")
            if finding is not None:
                return finding
        return None
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            finding = find_sensitive_value(item, path=f"{path}[{index}]")
            if finding is not None:
                return finding
        return None
    if isinstance(value, str) and (
        SECRET_MATERIAL.search(value)
        or CREDENTIAL_REFERENCE.search(value)
        or CONTACT_PII.search(value)
    ):
        return "secret or PII value", path
    if (
        isinstance(value, str)
        and "digest" not in path.casefold()
        and (PII_VALUE.search(value) or _contains_payment_card_number(value))
    ):
        return "PII value", path
    return None


def redact_sensitive(value: object) -> object:
    """Return a display-safe copy using the same rules as governed persistence."""
    if isinstance(value, dict):
        return {
            key: (
                "[redacted]"
                if _is_forbidden_key(key)
                else redact_sensitive(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str) and find_sensitive_value(value) is not None:
        return "[redacted]"
    return value


def _is_forbidden_key(key: str) -> bool:
    normalized = _KEY_SEPARATOR.sub(
        "_", _CAMEL_CASE_BOUNDARY.sub("_", key)
    ).strip("_").casefold()
    return (
        normalized in FORBIDDEN_KEYS
        or normalized.replace("_", "") in _FORBIDDEN_COMPACT_KEYS
    )


def _luhn_prefix_sums(digits: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return Luhn weight prefix sums, one per parity of the window's end.

    付款文件裡到處是十幾位數的訂單／商店編號,長度與分隔符和卡號無異,
    Luhn 是唯一能把兩者分開的確定性判準。一個數字要不要加倍,只取決於
    它自己的位置與窗尾位置的奇偶,不取決於窗從哪裡開始 —— 所以整段數字
    算兩條前綴和之後,任何一個窗都是一次減法。切窗是逐段候選都要做的事,
    沒有這個等式它是位數乘窗數。
    """
    even = [0]
    odd = [0]
    for index, character in enumerate(digits):
        digit = int(character)
        doubled = digit * 2 - 9 if digit > 4 else digit * 2
        even.append(even[-1] + (doubled if index % 2 == 0 else digit))
        odd.append(odd[-1] + (doubled if index % 2 == 1 else digit))
    return tuple(even), tuple(odd)


def _luhn_checksum(
    sums: tuple[tuple[int, ...], tuple[int, ...]], start: int, end: int
) -> int:
    return sums[end % 2][end] - sums[end % 2][start]


def iter_payment_card_numbers(text: str) -> Iterator[tuple[int, str]]:
    """Yield `(offset, digits)` for every Luhn-valid card number in `text`.

    候選樣式是貪婪的,所以一段候選不等於一個卡號:同一行內緊鄰的訂單編號
    會被吃進同一段候選,Luhn 對整串失敗,而 `finditer` 從候選結尾繼續掃,
    裡面的真卡號不會有第二次機會(`| 1 | 4539… |` 因為表格分隔而倖存,
    純文字編號清單則整筆漏掉)。所以逐段候選再切窗:候選內部的數字群是
    切點,依序取最長的合格窗,命中後從窗尾繼續,同一段數字只報一次
    (候選最多 19 位數,所以第二個窗在實務上不存在,續掃是為了不假設)。

    切點只落在數字群邊界:從一串數字中間切開會憑空造出卡號,而不是找出
    寫在來源裡的那一個 —— 代價是 `9994539148803436004` 這種沒有分隔符
    直接黏上去的形狀仍然掃不到,那是刻意的取捨。
    """
    for candidate in PAYMENT_CARD_CANDIDATE.finditer(text):
        yield from _payment_cards_within(candidate.group(), candidate.start())


def _payment_cards_within(
    candidate: str, offset: int
) -> Iterator[tuple[int, str]]:
    groups = [
        (match.start(), match.group())
        for match in _DIGIT_GROUP.finditer(candidate)
    ]
    digits = "".join(group for _, group in groups)
    # 窗的邊界只能落在數字群的邊界上,所以切點就是每個群的起始位數與總位數。
    cuts = [0]
    for _, group in groups:
        cuts.append(cuts[-1] + len(group))
    sums = _luhn_prefix_sums(digits)

    start = 0
    while start < len(groups):
        end = _card_window_from(sums, cuts, start)
        if end is None:
            start += 1
            continue
        yield offset + groups[start][0], digits[cuts[start] : cuts[end]]
        start = end


def _card_window_from(
    sums: tuple[tuple[int, ...], tuple[int, ...]],
    cuts: list[int],
    start: int,
) -> int | None:
    """Return the end cut of the longest Luhn-valid window starting at `start`.

    最長優先,因為卡號是連續寫出來的,較短的合格窗多半是把它截斷。取捨在
    於這個窗可能是把旁邊的編號吃進來湊出來的(`88 4111…` 約十分之一會通過
    Luhn);判斷「這其實是公告測試卡號」需要清單,那是取用端的政策,不是
    切窗的職責 —— `source_risk/` 據此豁免,治理端則兩者都拒。
    """
    for end in range(len(cuts) - 1, start, -1):
        length = cuts[end] - cuts[start]
        if length > 19:
            continue
        if length < 13:
            return None
        if _luhn_checksum(sums, cuts[start], cuts[end]) % 10 == 0:
            return end
    return None


def _contains_payment_card_number(value: str) -> bool:
    return next(iter_payment_card_numbers(value), None) is not None


#: 憑證性的參數／欄位名稱。與 `FORBIDDEN_KEYS` 分開:那組是治理酬載裡「不得
#: 出現」的欄位名(含低熵 PII),這組回答的是另一個問題 —— 一個 URL query key
#: 的「值」是不是憑證。兩者重疊但不相等,合併會讓 `?email=` 被當成憑證遮蔽,
#: 或讓 `sig` 混進治理端的禁用欄位。
#:
#: 比對方式刻意不對稱:長而明確的形狀用子字串比對,因為憑證 key 幾乎總是帶
#: 廠商前綴(`X-Amz-Signature`、`X-Goog-Signature`),精確集合會全數漏掉 ——
#: 而漏掉的代價是靜默洩漏。短而歧義的名稱用完整比對,因為 `key` 會吃掉
#: `keywords`,`code` 會吃掉 `country_code`,而誤遮的代價是 provenance 讀不懂。
CREDENTIAL_KEY_MARKERS = (
    "signature",
    "credential",
    "secret",
    "password",
    "passwd",
    "apikey",
    "accesskey",
    "privatekey",
    "token",
    "bearer",
    "authorization",
    "sessionid",
    "sessionkey",
    "sessid",
    "ticket",
)

CREDENTIAL_KEY_NAMES = frozenset(
    {"key", "sig", "code", "auth", "pwd", "pass", "token", "secret", "signature"}
)


def is_credential_key(key: str) -> bool:
    """名稱本身就表明其值是憑證。純函式,大小寫與分隔符無關。"""
    compact = _KEY_SEPARATOR.sub("", key).lower()
    if compact in CREDENTIAL_KEY_NAMES:
        return True
    return any(marker in compact for marker in CREDENTIAL_KEY_MARKERS)
