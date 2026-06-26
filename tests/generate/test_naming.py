from __future__ import annotations

import re

from loop_apidoc.generate.naming import security_scheme_key

_OK = re.compile(r"^[A-Za-z0-9._-]+$")


def test_sanitizes_spaces_parens_slashes():
    key = security_scheme_key("AES256 Encryption (TradeInfo / EncryptData_)", 0)
    assert _OK.match(key)
    assert key == "AES256_Encryption_TradeInfo_EncryptData"


def test_keeps_already_valid_name():
    assert security_scheme_key("CheckCode.Verification-1", 0) == "CheckCode.Verification-1"


def test_falls_back_when_empty_or_all_invalid():
    assert security_scheme_key("", 3) == "scheme3"
    assert security_scheme_key("（）／", 2) == "scheme2"
    assert security_scheme_key(None, 1) == "scheme1"


def test_deterministic():
    name = "SHA256 Request Signing (TradeSha / HashData_)"
    assert security_scheme_key(name, 0) == security_scheme_key(name, 9)
