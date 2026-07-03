from __future__ import annotations

import json
from pathlib import Path

import pytest

from loop_apidoc.preparation.coverage import (
    CoverageInputError,
    ResultStatus,
    UrlCoverage,
    load_coverage,
    normalize_url,
)


def _valid_payload() -> dict:
    return {
        "entry_url": "https://docs.example.com/api/",
        "confirmed_by_user": True,
        "expected": [
            {"url": "https://docs.example.com/api/auth", "title": "驗證", "source": "nav"}
        ],
        "results": [
            {
                "url": "https://docs.example.com/api/auth",
                "status": "fetched",
                "file": "url_sources/auth.md",
                "method": "defuddle",
            }
        ],
    }


def _write(tmp_path: Path, data) -> Path:
    path = tmp_path / "coverage.json"
    path.write_text(
        data if isinstance(data, str) else json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_load_valid_coverage_round_trips(tmp_path):
    coverage = load_coverage(_write(tmp_path, _valid_payload()))
    assert isinstance(coverage, UrlCoverage)
    assert coverage.entry_url == "https://docs.example.com/api/"
    assert coverage.confirmed_by_user is True
    assert coverage.expected[0].source.value == "nav"
    assert coverage.results[0].status is ResultStatus.FETCHED


def test_confirmed_by_user_defaults_false_when_absent(tmp_path):
    payload = _valid_payload()
    del payload["confirmed_by_user"]
    coverage = load_coverage(_write(tmp_path, payload))
    assert coverage.confirmed_by_user is False


def test_load_rejects_unknown_status(tmp_path):
    payload = _valid_payload()
    payload["results"][0]["status"] = "totally_made_up"
    with pytest.raises(CoverageInputError):
        load_coverage(_write(tmp_path, payload))


def test_load_rejects_missing_entry_url(tmp_path):
    payload = _valid_payload()
    del payload["entry_url"]
    with pytest.raises(CoverageInputError):
        load_coverage(_write(tmp_path, payload))


def test_load_rejects_unknown_key(tmp_path):
    payload = _valid_payload()
    payload["results"][0]["bogus"] = 1
    with pytest.raises(CoverageInputError):
        load_coverage(_write(tmp_path, payload))


def test_load_rejects_invalid_json(tmp_path):
    with pytest.raises(CoverageInputError):
        load_coverage(_write(tmp_path, "{not json"))


def test_load_rejects_missing_file(tmp_path):
    with pytest.raises(CoverageInputError):
        load_coverage(tmp_path / "does-not-exist.json")


def test_normalize_url_strips_fragment_and_trailing_slash():
    assert normalize_url("https://a.example/doc/") == "https://a.example/doc"
    assert normalize_url("https://a.example/doc#sec-2") == "https://a.example/doc"
    assert normalize_url("https://a.example/doc/#top") == "https://a.example/doc"
    # 同頁異寫正規化後相等
    assert normalize_url("https://a.example/p/") == normalize_url("https://a.example/p#x")
