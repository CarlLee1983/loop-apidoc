from __future__ import annotations

import json
from pathlib import Path

from loop_apidoc.html_snapshot import normalize_html_snapshot


def test_normalize_html_snapshot_keeps_the_credential_out_of_its_sidecar(tmp_path: Path):
    """Issue #156. A hand-built sidecar dict, the same shape as
    `gitbook_llms._write_sidecar` — the annotated-model seam does not reach it."""
    raw = tmp_path / "page.html"
    raw.write_text("<html><body><p>Hi</p></body></html>", encoding="utf-8")

    sidecar = normalize_html_snapshot(
        raw,
        "https://docs.example.com/guide?X-Amz-Signature=s3cret&page=2",
        tmp_path / "guide.md",
    )

    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["url"] == (
        "https://docs.example.com/guide?X-Amz-Signature=[REDACTED]&page=2"
    )
