from __future__ import annotations

import pytest

from loop_apidoc.url_adapters import resolve_fetch_url


@pytest.mark.parametrize(
    "url",
    [
        "https://hackmd.io/GExmbK-TRfejmexd-_X7Pw",
        "https://hackmd.io/GExmbK-TRfejmexd-_X7Pw/",
        "https://hackmd.io/@team/atg-api",
    ],
)
def test_hackmd_note_resolves_to_its_raw_markdown_representation(url):
    target = resolve_fetch_url(url)

    assert target.url.endswith("/download")
    assert target.representation == "markdown"
    assert "text/markdown" in target.accept


def test_hackmd_download_url_is_left_unchanged():
    target = resolve_fetch_url("https://hackmd.io/GExmbK-TRfejmexd-_X7Pw/download")

    assert target.url == "https://hackmd.io/GExmbK-TRfejmexd-_X7Pw/download"
    assert target.representation == "markdown"


def test_hackmd_fragment_is_dropped_because_raw_markdown_has_no_anchors():
    target = resolve_fetch_url("https://hackmd.io/GExmbK-TRfejmexd-_X7Pw#games")

    assert target.url == "https://hackmd.io/GExmbK-TRfejmexd-_X7Pw/download"


def test_hackmd_ui_route_is_not_treated_as_a_note():
    target = resolve_fetch_url("https://hackmd.io/login")

    assert target.url == "https://hackmd.io/login"
    assert target.representation == "html"


def test_unknown_host_keeps_the_original_url_and_html_representation():
    target = resolve_fetch_url("https://docs.example.com/cn/transfer/introduction")

    assert target.url == "https://docs.example.com/cn/transfer/introduction"
    assert target.representation == "html"
    assert "text/html" in target.accept
