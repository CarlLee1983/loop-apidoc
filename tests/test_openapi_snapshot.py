from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from loop_apidoc.openapi_snapshot import OpenApiSnapshotError, snapshot_openapi_url


def test_snapshot_openapi_url_writes_immutable_source_and_coverage(tmp_path: Path):
    source = {
        "openapi": "3.0.4",
        "info": {"title": "Transfer Operator", "version": "1.0"},
        "paths": {},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept"].startswith("application/json")
        return httpx.Response(
            200,
            json=source,
            headers={"content-type": "application/json"},
        )

    sources = tmp_path / "sources"
    coverage = tmp_path / "work" / "url_sources" / "coverage.json"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = snapshot_openapi_url(
            "https://spec.example.com/transfer/openapi.json",
            sources=sources,
            coverage_output=coverage,
            client=client,
        )

    snapshot = sources / "openapi.json"
    assert snapshot.is_file()
    assert json.loads(snapshot.read_text(encoding="utf-8")) == source
    assert result.snapshot_path == snapshot
    assert len(result.sha256) == 64
    ledger = json.loads(coverage.read_text(encoding="utf-8"))
    assert ledger == {
        "entry_url": "https://spec.example.com/transfer/openapi.json",
        "confirmed_by_user": False,
        "expected": [{
            "url": "https://spec.example.com/transfer/openapi.json",
            "title": "Transfer Operator",
            "source": "user",
        }],
        "results": [{
            "url": "https://spec.example.com/transfer/openapi.json",
            "status": "fetched",
            "file": "sources/openapi.json",
            "method": "direct",
        }],
    }


def test_snapshot_openapi_url_rejects_non_openapi_without_writing(tmp_path: Path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"info": {"title": "not a spec"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        try:
            snapshot_openapi_url(
                "https://spec.example.com/not-openapi.json",
                sources=tmp_path / "sources",
                coverage_output=tmp_path / "coverage.json",
                client=client,
            )
        except ValueError as exc:
            assert "OpenAPI" in str(exc)
        else:
            raise AssertionError("expected non-OpenAPI document to be rejected")

    assert not (tmp_path / "sources").exists()
    assert not (tmp_path / "coverage.json").exists()


@pytest.mark.parametrize(
    ("url", "filename", "content_type", "content", "message"),
    [
        (
            "https://spec.example.com/openapi.json",
            "../escape.json",
            "application/json",
            b'{"openapi":"3.0.4"}',
            "filename must be a single file name",
        ),
        (
            "https://spec.example.com/openapi.json",
            None,
            "application/json",
            b"{not json",
            "response is not valid OpenAPI JSON/YAML",
        ),
        (
            "https://spec.example.com/openapi.yaml",
            None,
            "application/yaml",
            b"openapi: [unclosed",
            "response is not valid OpenAPI JSON/YAML",
        ),
        (
            "https://spec.example.com/openapi.json",
            None,
            "application/json",
            b"\xff",
            "response is not UTF-8 JSON/YAML",
        ),
        (
            "https://spec.example.com/openapi.json",
            None,
            "application/json",
            b"[]",
            "OpenAPI document root must be an object",
        ),
    ],
    ids=["nested-filename", "malformed-json", "malformed-yaml", "non-utf8", "list-root"],
)
def test_snapshot_openapi_url_rejects_malformed_documents_without_writing(
    tmp_path: Path,
    url: str,
    filename: str | None,
    content_type: str,
    content: bytes,
    message: str,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"content-type": content_type})

    sources = tmp_path / "sources"
    coverage = tmp_path / "coverage.json"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OpenApiSnapshotError, match=message):
            snapshot_openapi_url(
                url,
                sources=sources,
                coverage_output=coverage,
                filename=filename,
                client=client,
            )

    assert not sources.exists()
    assert not coverage.exists()


def test_snapshot_openapi_url_uses_yaml_content_type_for_deterministic_default_name(
    tmp_path: Path,
) -> None:
    content = b"openapi: 3.0.4\ninfo:\n  title: YAML API\npaths: {}\n"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"content-type": "application/yaml"})

    sources = tmp_path / "sources"
    coverage = tmp_path / "coverage.json"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = snapshot_openapi_url(
            "https://spec.example.com/v1/spec",
            sources=sources,
            coverage_output=coverage,
            client=client,
        )

    assert result.snapshot_path == sources / "openapi.yaml"
    assert result.snapshot_path.read_bytes() == content
    assert json.loads(coverage.read_text(encoding="utf-8"))["results"][0]["file"] == (
        "sources/openapi.yaml"
    )


def test_snapshot_openapi_url_honors_a_safe_explicit_filename(tmp_path: Path) -> None:
    content = b'{"openapi":"3.0.4","info":{"title":"Explicit name"},"paths":{}}'

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"content-type": "application/json"})

    sources = tmp_path / "sources"
    coverage = tmp_path / "coverage.json"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = snapshot_openapi_url(
            "https://spec.example.com/v1/spec",
            sources=sources,
            coverage_output=coverage,
            filename="provider-contract.json",
            client=client,
        )

    assert result.snapshot_path == sources / "provider-contract.json"
    assert result.snapshot_path.read_bytes() == content


@pytest.mark.parametrize("url", ["spec.example.com/openapi.json", "file:///tmp/openapi.json"])
def test_snapshot_openapi_url_rejects_non_http_absolute_urls_before_fetch(
    tmp_path: Path,
    url: str,
) -> None:
    with pytest.raises(OpenApiSnapshotError, match="absolute http\\(s\\) URL"):
        snapshot_openapi_url(
            url,
            sources=tmp_path / "sources",
            coverage_output=tmp_path / "coverage.json",
        )


def test_snapshot_openapi_url_rejects_nonpositive_byte_cap_before_fetch(tmp_path: Path) -> None:
    with pytest.raises(OpenApiSnapshotError, match="max_bytes must be positive"):
        snapshot_openapi_url(
            "https://spec.example.com/openapi.json",
            sources=tmp_path / "sources",
            coverage_output=tmp_path / "coverage.json",
            max_bytes=0,
        )


def test_snapshot_openapi_url_wraps_fetch_errors_and_closes_owned_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingClient:
        closed = False

        def get(self, *_args: object, **_kwargs: object) -> httpx.Response:
            raise httpx.ConnectError("offline")

        def close(self) -> None:
            self.closed = True

    client = FailingClient()
    monkeypatch.setattr("loop_apidoc.openapi_snapshot.httpx.Client", lambda **_kwargs: client)

    with pytest.raises(OpenApiSnapshotError, match="fetch failed: ConnectError"):
        snapshot_openapi_url(
            "https://spec.example.com/openapi.json",
            sources=tmp_path / "sources",
            coverage_output=tmp_path / "coverage.json",
        )

    assert client.closed is True


def test_snapshot_openapi_url_rejects_response_over_byte_cap_without_writing(
    tmp_path: Path,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"openapi":"3.0.4"}')

    sources = tmp_path / "sources"
    coverage = tmp_path / "coverage.json"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OpenApiSnapshotError, match="response exceeded 1 byte cap"):
            snapshot_openapi_url(
                "https://spec.example.com/openapi.json",
                sources=sources,
                coverage_output=coverage,
                max_bytes=1,
                client=client,
            )

    assert not sources.exists()
    assert not coverage.exists()


def test_snapshot_openapi_url_rejects_overlapping_outputs_without_writing(
    tmp_path: Path,
):
    source = {
        "openapi": "3.0.4",
        "info": {"title": "Protected API", "version": "1.0"},
        "paths": {},
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=source,
            headers={"content-type": "application/json"},
        )

    sources = tmp_path / "sources"
    overlapping_output = sources / "openapi.json"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OpenApiSnapshotError, match="must be distinct"):
            snapshot_openapi_url(
                "https://spec.example.com/openapi.json",
                sources=sources,
                coverage_output=overlapping_output,
                client=client,
            )

    assert not sources.exists()


@pytest.mark.parametrize(
    "coverage_is_ancestor",
    [True, False],
    ids=["coverage-ancestor", "sources-ancestor"],
)
def test_snapshot_openapi_url_rejects_ancestor_overlap_without_writing(
    tmp_path: Path,
    coverage_is_ancestor: bool,
) -> None:
    source = {
        "openapi": "3.0.4",
        "info": {"title": "Protected API", "version": "1.0"},
        "paths": {},
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=source,
            headers={"content-type": "application/json"},
        )

    if coverage_is_ancestor:
        coverage = tmp_path / "output"
        sources = coverage / "sources"
    else:
        sources = tmp_path / "sources"
        coverage = sources / "url_sources" / "coverage.json"

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OpenApiSnapshotError, match="must not overlap"):
            snapshot_openapi_url(
                "https://spec.example.com/openapi.json",
                sources=sources,
                coverage_output=coverage,
                client=client,
            )

    assert not sources.exists()


@pytest.mark.parametrize(
    "blocked_output",
    ["snapshot", "coverage"],
)
def test_snapshot_openapi_url_rejects_dangling_output_symlinks_without_writing(
    tmp_path: Path,
    blocked_output: str,
) -> None:
    source = {
        "openapi": "3.0.4",
        "info": {"title": "Protected API", "version": "1.0"},
        "paths": {},
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=source,
            headers={"content-type": "application/json"},
        )

    sources = tmp_path / "sources"
    snapshot = sources / "openapi.json"
    coverage = tmp_path / "work" / "url_sources" / "coverage.json"
    blocked = snapshot if blocked_output == "snapshot" else coverage
    counterpart = coverage if blocked_output == "snapshot" else snapshot
    blocked.parent.mkdir(parents=True)
    blocked.symlink_to("missing-target")
    symlink_target = blocked.parent / "missing-target"

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OpenApiSnapshotError, match="already exists"):
            snapshot_openapi_url(
                "https://spec.example.com/openapi.json",
                sources=sources,
                coverage_output=coverage,
                client=client,
            )

    assert blocked.is_symlink()
    assert blocked.readlink() == Path("missing-target")
    assert not symlink_target.exists()
    assert not counterpart.exists()


@pytest.mark.parametrize(
    "raced_output",
    ["snapshot", "coverage"],
)
def test_snapshot_openapi_url_preserves_output_created_during_staging(
    tmp_path: Path,
    raced_output: str,
) -> None:
    source = {
        "openapi": "3.0.4",
        "info": {"title": "Protected API", "version": "1.0"},
        "paths": {},
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=source,
            headers={"content-type": "application/json"},
        )

    sources = tmp_path / "sources"
    snapshot = sources / "openapi.json"
    coverage = tmp_path / "work" / "url_sources" / "coverage.json"
    raced = snapshot if raced_output == "snapshot" else coverage
    counterpart = coverage if raced_output == "snapshot" else snapshot
    competing_bytes = b"created by another process"

    def stage_with_competing_output(target: Path, content: bytes) -> Path:
        staged = target.with_name(f".{target.name}.staged")
        staged.write_bytes(content)
        if target == raced:
            target.write_bytes(competing_bytes)
        return staged

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OpenApiSnapshotError, match="already exists"):
            snapshot_openapi_url(
                "https://spec.example.com/openapi.json",
                sources=sources,
                coverage_output=coverage,
                client=client,
                stage_file=stage_with_competing_output,
            )

    assert raced.read_bytes() == competing_bytes
    assert not counterpart.exists()
    assert sorted(path.name for path in raced.parent.iterdir()) == [raced.name]


def test_snapshot_openapi_url_rollback_preserves_replaced_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = {
        "openapi": "3.0.4",
        "info": {"title": "Protected API", "version": "1.0"},
        "paths": {},
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=source,
            headers={"content-type": "application/json"},
        )

    sources = tmp_path / "sources"
    snapshot = sources / "openapi.json"
    coverage = tmp_path / "work" / "url_sources" / "coverage.json"
    replacement_bytes = b"replacement from another process"
    competing_coverage = b"competing coverage"
    real_link = os.link

    def link_with_replacement(source_path: Path, target_path: Path) -> None:
        target = Path(target_path)
        if target == coverage:
            snapshot.unlink()
            snapshot.write_bytes(replacement_bytes)
            coverage.write_bytes(competing_coverage)
        real_link(source_path, target_path)

    monkeypatch.setattr(
        "loop_apidoc.openapi_snapshot.os.link",
        link_with_replacement,
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OpenApiSnapshotError, match="already exists"):
            snapshot_openapi_url(
                "https://spec.example.com/openapi.json",
                sources=sources,
                coverage_output=coverage,
                client=client,
            )

    assert snapshot.read_bytes() == replacement_bytes
    assert coverage.read_bytes() == competing_coverage
    assert sorted(path.name for path in sources.iterdir()) == [snapshot.name]


def test_snapshot_openapi_url_rollback_tolerates_removed_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = {
        "openapi": "3.0.4",
        "info": {"title": "Protected API", "version": "1.0"},
        "paths": {},
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=source,
            headers={"content-type": "application/json"},
        )

    sources = tmp_path / "sources"
    snapshot = sources / "openapi.json"
    coverage = tmp_path / "work" / "url_sources" / "coverage.json"
    competing_coverage = b"competing coverage"
    real_link = os.link

    def link_after_snapshot_removal(source_path: Path, target_path: Path) -> None:
        target = Path(target_path)
        if target == coverage:
            snapshot.unlink()
            coverage.write_bytes(competing_coverage)
        real_link(source_path, target_path)

    monkeypatch.setattr(
        "loop_apidoc.openapi_snapshot.os.link",
        link_after_snapshot_removal,
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OpenApiSnapshotError, match="already exists"):
            snapshot_openapi_url(
                "https://spec.example.com/openapi.json",
                sources=sources,
                coverage_output=coverage,
                client=client,
            )

    assert not snapshot.exists()
    assert coverage.read_bytes() == competing_coverage
    assert list(sources.iterdir()) == []


def test_snapshot_openapi_url_keeps_the_credential_out_of_the_coverage_ledger(tmp_path: Path):
    """Issue #156. A signed spec link is the motivating case for this whole
    control: the credential is needed to fetch and must not survive the write."""
    signed = "https://spec.example.com/openapi.json?X-Goog-Signature=s3cret&v=3"
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            200,
            json={"openapi": "3.0.4", "info": {"title": "T", "version": "1"}, "paths": {}},
            headers={"content-type": "application/json"},
        )

    coverage = tmp_path / "coverage.json"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        snapshot_openapi_url(
            signed,
            sources=tmp_path / "sources",
            coverage_output=coverage,
            client=client,
        )

    assert requested == [signed]
    written = coverage.read_text(encoding="utf-8")
    assert "s3cret" not in written
    assert "X-Goog-Signature=[REDACTED]" in written
    assert "v=3" in written


def test_snapshot_openapi_url_does_not_put_the_fetched_url_in_its_error(tmp_path: Path):
    """Issue #156. `httpx.HTTPStatusError` stringifies as "... for url '<full
    url>'", so interpolating the exception writes the credential to stderr and
    into any CI log. `gitbook_llms` already reports the class name only."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="nope")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OpenApiSnapshotError) as raised:
            snapshot_openapi_url(
                "https://spec.example.com/openapi.json?token=s3cret",
                sources=tmp_path / "sources",
                coverage_output=tmp_path / "coverage.json",
                client=client,
            )

    assert "s3cret" not in str(raised.value)
