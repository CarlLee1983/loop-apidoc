from __future__ import annotations

from loop_apidoc.extraction.jsonblock import extract_json_block, find_gaps


def test_extract_labeled_json_block():
    text = 'Here you go:\n```json\n{"endpoints": [], "missing": ["auth"]}\n```\nThanks.'
    block = extract_json_block(text)
    assert block == {"endpoints": [], "missing": ["auth"]}


def test_extract_unlabeled_block_fallback():
    text = "```\n{\"a\": 1}\n```"
    assert extract_json_block(text) == {"a": 1}


def test_extract_returns_none_when_absent():
    assert extract_json_block("The sources do not provide this.") is None


def test_extract_returns_none_on_invalid_json():
    assert extract_json_block("```json\n{not valid}\n```") is None


def test_extract_returns_none_when_block_is_not_object():
    assert extract_json_block("```json\n[1, 2, 3]\n```") is None


def test_find_gaps_collects_nulls_and_missing():
    block = {"base_url": None, "version": "v1", "missing": ["signing", "base_url"]}
    gaps = find_gaps(block)
    assert gaps == ["base_url", "signing"]


def test_find_gaps_empty_when_complete():
    assert find_gaps({"x": 1, "missing": []}) == []
