from __future__ import annotations

import re

from loop_apidoc.generate.naming import security_scheme_key, webhook_name

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


def test_webhook_name_cuts_at_first_parenthetical_or_newline():
    # Pre-existing behaviour: the leading label before a parenthetical qualifier.
    assert webhook_name("Backend Notify (webhook). After a tx completes...", 0) == "Backend Notify"
    assert webhook_name("付款結果通知（綠界 POST…）", 0) == "付款結果通知"
    assert webhook_name("label\nmore", 0) == "label"


def test_webhook_name_cuts_at_first_sentence_or_colon_boundary():
    # A whole-paragraph summary (no early paren) must NOT become the webhook key;
    # take the leading clause before the first sentence/colon boundary so the key
    # stays a concise identifier. (GitHub/Stripe list many events as prose.)
    assert webhook_name(
        "push webhook event. Sent when one or more commits are pushed to a branch.", 0
    ) == "push webhook event"
    assert webhook_name("star: repository was starred or unstarred", 0) == "star"
    assert webhook_name("付款完成。後續會回傳通知", 0) == "付款完成"


def test_webhook_name_falls_back_when_empty():
    assert webhook_name("", 5) == "webhook5"
    assert webhook_name(None, 2) == "webhook2"
