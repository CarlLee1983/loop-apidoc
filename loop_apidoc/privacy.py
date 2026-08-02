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
_SECRET_VALUE = re.compile(
    r"(?i)(?:\bbearer\s+\S+|\bbasic\s+\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b|"
    r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b|"
    r"\b(?:password|passwd|secret|client[_-]?secret|access[_-]?token|"
    r"refresh[_-]?token|api[_-]?key|authorization|cookie)\s*[:=]\s*\S+)"
)
_PII_VALUE = re.compile(
    r"(?i)(?:\b[A-Z][12]\d{8}\b|"
    r"(?<!\d)\d{3}[-.\s]\d{2}[-.\s]\d{4}(?!\d)|"
    r"\b(?:passport(?:\s+(?:number|no\.?))?|ssn|social[ -]?security(?:\s+number)?)"
    r"\s*[:#=\-]?\s*[A-Z0-9-]{6,20}\b|"
    r"(?<!\d)(?:\+886[-.\s]?|0)9\d{2}[-.\s]?\d{3}[-.\s]?\d{3}(?!\d)|"
    r"(?<!\d)(?:\+886[-.\s]?|0)\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)|"
    r"(?<!\w)\+\d(?:[-.\s]?\d){7,14}(?!\d))"
)
_PAYMENT_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[-.\s]?){12,18}\d(?!\d)")


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
    if isinstance(value, str) and _SECRET_VALUE.search(value):
        return "secret or PII value", path
    if (
        isinstance(value, str)
        and "digest" not in path.casefold()
        and (_PII_VALUE.search(value) or _contains_payment_card_number(value))
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


def _contains_payment_card_number(value: str) -> bool:
    for candidate in _PAYMENT_CARD_CANDIDATE.finditer(value):
        digits = [int(character) for character in candidate.group() if character.isdigit()]
        if not 13 <= len(digits) <= 19:
            continue
        checksum = 0
        parity = len(digits) % 2
        for index, digit in enumerate(digits):
            if index % 2 == parity:
                digit *= 2
                if digit > 9:
                    digit -= 9
            checksum += digit
        if checksum % 10 == 0:
            return True
    return False
