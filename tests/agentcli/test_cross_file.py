from __future__ import annotations

from loop_apidoc.agentcli.cross_file import cross_file_violations


def _inv(*endpoints: dict, schemas=(), security_schemes=()) -> dict:
    return {
        "endpoints": list(endpoints),
        "schemas": [{"name": n} for n in schemas],
        "security_schemes": [{"name": n} for n in security_schemes],
    }


def _ep(method: str = "GET", path: str = "/ping", **extra) -> dict:
    return {"method": method, "path": path, **extra}


def test_clean_extraction_has_no_violations():
    inventory = _inv(_ep("GET", "/ping"), _ep("POST", "/orders"))
    endpoints = [("ep0.json", _ep("GET", "/ping")),
                 ("ep1.json", _ep("POST", "/orders"))]

    assert cross_file_violations(inventory, endpoints) == []


def test_method_case_is_normalized():
    inventory = _inv(_ep("get", "/ping"))
    endpoints = [("ep0.json", _ep("GET", "/ping"))]

    assert cross_file_violations(inventory, endpoints) == []


# ── 不變式 1:數量 ────────────────────────────────────────────────────

def test_missing_endpoint_file_is_a_violation():
    """一個 subagent 死掉、什麼都沒寫。"""
    inventory = _inv(_ep("GET", "/ping"), _ep("POST", "/orders"))
    endpoints = [("ep0.json", _ep("GET", "/ping"))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("1" in v and "2" in v for v in violations)
    assert any("endpoints/*.json" in v for v in violations)


# ── 不變式 2:(method, path) 多重集合相等 ─────────────────────────────

def test_endpoint_file_not_in_inventory_is_a_violation():
    inventory = _inv(_ep("GET", "/ping"))
    endpoints = [("ep0.json", _ep("GET", "/pong"))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("GET /pong" in v and "ep0.json" in v for v in violations)


def test_inventory_endpoint_with_no_file_is_a_violation():
    inventory = _inv(_ep("GET", "/ping"), _ep("POST", "/orders"))
    endpoints = [("ep0.json", _ep("GET", "/ping")), ("ep1.json", _ep("GET", "/ping"))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("POST /orders" in v for v in violations)


# ── 不變式 3:端點檔之間不得重複 ───────────────────────────────────────

def test_two_files_writing_the_same_endpoint_is_a_violation():
    """真正會掉資料的失效模式:兩個 subagent 寫同一個端點,第三個端點沒人寫。"""
    inventory = _inv(_ep("GET", "/ping"), _ep("POST", "/orders"))
    endpoints = [("ep0.json", _ep("GET", "/ping")), ("ep1.json", _ep("GET", "/ping"))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("ep0.json" in v and "ep1.json" in v and "GET /ping" in v
               for v in violations)


def test_duplicate_endpoint_is_not_reported_as_missing_from_inventory():
    """重複寫入的端點確實在 inventory 中 —— 只能報「重複」,不可報「不在 inventory」。"""
    inventory = _inv(_ep("GET", "/ping"), _ep("POST", "/orders"))
    endpoints = [("ep0.json", _ep("GET", "/ping")), ("ep1.json", _ep("GET", "/ping"))]

    violations = cross_file_violations(inventory, endpoints)

    assert not any("不在 inventory.endpoints" in v for v in violations)
    assert any("被寫進多個檔案" in v for v in violations)
    assert any("POST /orders" in v for v in violations)


# ── 不變式 4:schema_ref 必須指向 inventory.schemas[].name ─────────────

def test_request_schema_ref_must_resolve():
    inventory = _inv(_ep(), schemas=("Order",))
    endpoints = [("ep0.json", _ep(request={"schema_ref": "Ordr"}))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("ep0.json" in v and "schema_ref" in v and "Ordr" in v
               for v in violations)


def test_response_schema_ref_must_resolve():
    inventory = _inv(_ep(), schemas=("Order",))
    endpoints = [("ep0.json", _ep(responses=[{"status": "200", "schema_ref": "Nope"}]))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("responses[0].schema_ref" in v for v in violations)


def test_resolving_schema_refs_pass():
    inventory = _inv(_ep(), schemas=("Order",))
    endpoints = [("ep0.json", _ep(request={"schema_ref": "Order"},
                                  responses=[{"schema_ref": "Order"}]))]

    assert cross_file_violations(inventory, endpoints) == []


def test_null_schema_ref_is_allowed():
    inventory = _inv(_ep())
    endpoints = [("ep0.json", _ep(request={"schema_ref": None}, responses=[{}]))]

    assert cross_file_violations(inventory, endpoints) == []


# ── 不變式 5:security[] 必須指向 inventory.security_schemes[].name ────

def test_unknown_security_scheme_is_a_violation():
    inventory = _inv(_ep(), security_schemes=("apiKey",))
    endpoints = [("ep0.json", _ep(security=["oauth2"]))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("ep0.json" in v and "security[0]" in v and "oauth2" in v
               for v in violations)


def test_known_security_scheme_passes():
    inventory = _inv(_ep(), security_schemes=("apiKey",))
    endpoints = [("ep0.json", _ep(security=["apiKey"]))]

    assert cross_file_violations(inventory, endpoints) == []


# ── null path 端點(webhook/callback)豁免多重集合與重複檢查 ──────────────

def _null_ep(**extra) -> dict:
    return {"method": "POST", "path": None, **extra}


def test_multiple_null_path_endpoints_are_not_flagged():
    """GitHub-webhooks 的形狀:多筆 path: null 端點,彼此無法用 (method, path) 區分。"""
    inventory = _inv(_null_ep(), _null_ep(), _null_ep())
    endpoints = [
        ("ep0.json", _null_ep()),
        ("ep1.json", _null_ep()),
        ("ep2.json", _null_ep()),
    ]

    assert cross_file_violations(inventory, endpoints) == []


def test_mix_of_real_and_null_path_endpoints_is_not_flagged():
    inventory = _inv(_ep("POST", "/orders"), _null_ep(), _null_ep())
    endpoints = [
        ("ep0.json", _ep("POST", "/orders")),
        ("ep1.json", _null_ep()),
        ("ep2.json", _null_ep()),
    ]

    assert cross_file_violations(inventory, endpoints) == []


def test_duplicate_real_path_endpoint_is_still_reported():
    """迴歸守門:真實 path 的重複仍要被抓到,不因 null path 豁免而連帶失效。"""
    inventory = _inv(_ep("GET", "/ping"), _null_ep())
    endpoints = [
        ("ep0.json", _ep("GET", "/ping")),
        ("ep1.json", _ep("GET", "/ping")),
        ("ep2.json", _null_ep()),
    ]

    violations = cross_file_violations(inventory, endpoints)

    assert any("ep0.json" in v and "ep1.json" in v and "GET /ping" in v
               for v in violations)


def test_null_path_count_mismatch_is_still_caught_by_invariant_1():
    """迴歸守門:null path 檔數與 inventory 筆數不符,仍要靠不變式 1(總數)抓到。"""
    inventory = _inv(_null_ep(), _null_ep(), _null_ep())
    endpoints = [("ep0.json", _null_ep()), ("ep1.json", _null_ep())]

    violations = cross_file_violations(inventory, endpoints)

    assert any("2" in v and "3" in v and "endpoints/*.json" in v
               for v in violations)
