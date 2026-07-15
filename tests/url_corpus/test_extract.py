from __future__ import annotations

from loop_apidoc.url_corpus import extract_page_metadata


def test_extract_page_metadata_uses_main_content_not_repeated_navigation():
    metadata = extract_page_metadata(
        "https://docs.example.com/transfer/introduction",
        """
        <html><head><title>Fallback title</title></head><body>
          <aside><a href="/single/intro">Single wallet navigation</a></aside>
          <main>
            <h1>Transfer workflow</h1>
            <h2>Cash transfer</h2>
            <p>Use Action 19. Error 9005 means the request expired.</p>
            <a href="/transfer/action19">Action 19 detail</a>
          </main>
          <footer>Footer text</footer>
        </body></html>
        """,
    )

    assert metadata.title == "Transfer workflow"
    assert metadata.headings == ["Transfer workflow", "Cash transfer"]
    assert "Single wallet navigation" not in metadata.body_text
    assert "Footer text" not in metadata.body_text
    assert metadata.internal_links == ["https://docs.example.com/transfer/action19"]
    assert metadata.entities == ["action:19", "error:9005"]
