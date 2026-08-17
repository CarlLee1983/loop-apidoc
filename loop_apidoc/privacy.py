from __future__ import annotations

import re


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
SECRET_MATERIAL = re.compile(
    r"(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b)"
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
#: 卡號候選樣式。單獨使用會誤報訂單／商店編號 ——
#: 必須搭配 `is_payment_card_number` 的 Luhn 檢查。
#: 分隔符只排除換行,不排除其他 Unicode 空白 —— 卡號不會跨行,而允許跨行
#: 會把相鄰兩行的訂單編號接成長度合格的候選,再由 Luhn 隨機放行約十分之一。
#: 用 `[-. \t]` 一併排掉 NBSP 與全形空格則是另一個錯誤方向:從 PDF 貼出的
#: 付款範例帶 U+00A0、zh-TW 文件帶 U+3000,那會讓真卡號通過治理閘。
PAYMENT_CARD_CANDIDATE = re.compile(
    r"(?<!\d)(?:\d(?:[-.]|[^\S\r\n])?){12,18}\d(?!\d)"
)
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


def is_payment_card_number(candidate: str) -> bool:
    """Luhn-validate one digit run matched by `PAYMENT_CARD_CANDIDATE`.

    付款文件裡到處是十幾位數的訂單／商店編號,長度與分隔符和卡號無異。
    Luhn 是唯一能把兩者分開的確定性判準,所以候選樣式從不單獨使用。
    """
    digits = [int(character) for character in candidate if character.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _contains_payment_card_number(value: str) -> bool:
    return any(
        is_payment_card_number(candidate.group())
        for candidate in PAYMENT_CARD_CANDIDATE.finditer(value)
    )
