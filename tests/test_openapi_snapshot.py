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
