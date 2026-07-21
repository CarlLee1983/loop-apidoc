from __future__ import annotations

import json
from loop_apidoc.gitbook_llms import parse_llms_index


def test_parse_llms_index_keeps_safe_same_prefix_markdown_urls_once():
    index = """# Docs

- [Overview](https://docs.example.com/vg-docs/overview.md)
- [Transfer](https://docs.example.com/vg-docs/api/transfer.md#request)
- [Duplicate](https://docs.example.com/vg-docs/overview.md)
- [Duplicate destination](https://docs.example.com/vg-docs/overview.md?revision=2)
- [Other host](https://other.example.com/vg-docs/other.md)
- [Outside prefix](https://docs.example.com/other.md)
- [Asset](https://docs.example.com/vg-docs/logo.png)
- [Escape](https://docs.example.com/vg-docs/../secret.md)
"""

    parsed = parse_llms_index("https://docs.example.com/vg-docs", index)

    assert parsed.entry_url == "https://docs.example.com/vg-docs/"
    assert parsed.index_url == "https://docs.example.com/vg-docs/llms.txt"
    assert [(page.url, page.destination.as_posix()) for page in parsed.pages] == [
        ("https://docs.example.com/vg-docs/overview.md", "overview.md"),
        ("https://docs.example.com/vg-docs/api/transfer.md", "api/transfer.md"),
    ]


def test_parse_llms_index_supports_root_entry_and_rejects_unsafe_urls():
    index = """https://docs.example.com/a.md
https://docs.example.com/%2e%2e/secret.md
mailto:docs@example.com
/relative.md
"""

    parsed = parse_llms_index("https://docs.example.com", index)

    assert parsed.index_url == "https://docs.example.com/llms.txt"
    assert [(page.url, page.destination.as_posix()) for page in parsed.pages] == [
        ("https://docs.example.com/a.md", "a.md"),
    ]


def test_cache_gitbook_llms_preserves_paths_and_records_page_failures(tmp_path):
    import httpx

    from loop_apidoc.gitbook_llms import cache_gitbook_llms

    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/vg-docs/llms.txt":
            return httpx.Response(
                200,
                text=(
                    "[Overview](https://docs.example.com/vg-docs/overview.md)\n"
                    "[Transfer](https://docs.example.com/vg-docs/api/transfer.md)\n"
                ),
            )
        if request.url.path == "/vg-docs/overview.md":
            return httpx.Response(200, content=b"# Overview\n")
        return httpx.Response(503, text="unavailable")

    sources = tmp_path / "sources"
    coverage_path = tmp_path / "coverage.json"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = cache_gitbook_llms(
            "https://docs.example.com/vg-docs",
            sources=sources,
            coverage_output=coverage_path,
            client=client,
        )

    assert requests == [
        "https://docs.example.com/vg-docs/llms.txt",
        "https://docs.example.com/vg-docs/overview.md",
        "https://docs.example.com/vg-docs/api/transfer.md",
    ]
    assert result.fetched == 1
    assert result.failed == 1
    page = sources / "overview.md"
    assert page.read_text(encoding="utf-8") == "# Overview\n"
    sidecar = json.loads((sources / "overview.md.source.json").read_text(encoding="utf-8"))
    assert sidecar["url"] == "https://docs.example.com/vg-docs/overview.md"
    assert len(sidecar["content_sha256"]) == 64
    assert sidecar["fetched_at"].endswith("Z")
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    assert [item["url"] for item in coverage["expected"]] == [
        "https://docs.example.com/vg-docs/overview.md",
        "https://docs.example.com/vg-docs/api/transfer.md",
    ]
    assert [item["status"] for item in coverage["results"]] == ["fetched", "fetch_failed"]
    assert coverage["results"][1]["note"] == "HTTPStatusError"
