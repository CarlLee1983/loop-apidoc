from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from loop_apidoc.foundry import paths, register
from loop_apidoc.foundry.models import Docset
from loop_apidoc.review import ReviewDraft, ReviewRequest, ReviewWorkflow
from loop_apidoc.review.web import ReviewWebAdapter, _page
from tests.foundry._fixtures import write_run_dir


def _adapter(tmp_path: Path) -> ReviewWebAdapter:
    register.register_docset(
        tmp_path,
        Docset(docset_id="vendor-payments", title="Payments", provider="vendor", product="pay"),
    )
    run = write_run_dir(tmp_path / "output" / "20260723T120000.000000Z", validation_ok=False)
    workflow = ReviewWorkflow(tmp_path)
    snapshot = workflow.open_review(ReviewRequest(docset_id="vendor-payments", run_dir=run))
    return ReviewWebAdapter(workflow, snapshot)


def _request(url: str, *, method: str = "GET", body: object | None = None, token: str | None = None) -> tuple[int, object]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if token is not None:
        headers["X-Loop-Review-Token"] = token
    request = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=2) as response:
            raw = response.read()
            content_type = response.headers.get_content_type()
            return response.status, json.loads(raw) if content_type == "application/json" else raw.decode("utf-8")
    except HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw.decode("utf-8")


def _raw_request(
    url: str, *, method: str, body: bytes | None, headers: dict[str, str]
) -> tuple[int, object]:
    parsed = urlsplit(url)
    connection = HTTPConnection(parsed.hostname, parsed.port, timeout=2)
    try:
        connection.request(method, parsed.path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw)
    finally:
        connection.close()


def test_workbench_page_restores_saved_decisions_and_accepts_manual_items() -> None:
    page = _page("test-token")

    assert "const decision=s.decision||" in page
    assert "select.value=item?.disposition||''" in page
    assert "id=\"manual-items\"" in page
    assert "items:[...subjectItems,...manualItems]" in page
    assert "Candidate, current, and provenance artifacts" in page
    assert "renderArtifacts(s)" in page
    assert "binding:snapshot.binding" in page
    assert "renderEvidence(subject.evidence)" in page
    assert "normalized_excerpt" in page
    assert "core/projections/review-data.json" in page


def test_loopback_adapter_serves_fixed_snapshot_and_protects_writes(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    thread = threading.Thread(target=adapter.serve_forever, daemon=True)
    thread.start()
    try:
        status, page = _request(adapter.url)
        assert status == 200
        assert "API contract review" in page

        status, snapshot = _request(f"{adapter.url}api/review")
        assert status == 200
        assert snapshot["mode"] == "baseline"
        subject = snapshot["subjects"][0]

        status, payload = _request(
            f"{adapter.url}api/decision",
            method="PUT",
            body={"binding": snapshot["binding"], "items": [], "handoff": []},
        )
        assert status == 403
        assert payload["error"] == "invalid session token"

        status, payload = _request(
            f"{adapter.url}api/decision",
            method="PUT",
            token=adapter.token,
            body={
                "binding": snapshot["binding"],
                "items": [{
                    "subject_id": subject["id"],
                    "subject_kind": subject["kind"],
                    "disposition": "needs_evidence",
                }],
                "handoff": [],
            },
        )
        assert status == 200
        assert payload["decision"]["items"][0]["disposition"] == "needs_evidence"

        status, artifact = _request(f"{adapter.url}artifact/candidate/validation/report.json")
        assert status == 200
        assert artifact["issues"][0]["severity"] == "error"

        status, _ = _request(f"{adapter.url}artifact/candidate/%2E%2E%2Fsecret.txt")
        assert status == 404
    finally:
        adapter.shutdown()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_loopback_adapter_rejects_bad_routes_and_can_approve(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    thread = threading.Thread(target=adapter.serve_forever, daemon=True)
    thread.start()
    try:
        status, _ = _request(f"{adapter.url}not-a-route")
        assert status == 404

        status, _ = _request(f"{adapter.url}api/not-decision", method="PUT", body={})
        assert status == 404
        status, _ = _request(f"{adapter.url}api/not-approve", method="POST", body={})
        assert status == 404

        status, payload = _request(
            f"{adapter.url}api/decision",
            method="PUT",
            token=adapter.token,
            body={
                "binding": adapter.snapshot.binding.model_dump(mode="json"),
                "items": "not-a-list",
                "handoff": [],
            },
        )
        assert status == 422
        assert "items" in payload["error"]

        status, payload = _raw_request(
            f"{adapter.url}api/decision",
            method="PUT",
            body=b"{}",
            headers={
                "Content-Type": "application/json",
                "Content-Length": "not-a-number",
                "X-Loop-Review-Token": adapter.token,
            },
        )
        assert status == 400
        assert payload["error"] == "invalid content length"

        status, payload = _raw_request(
            f"{adapter.url}api/decision",
            method="PUT",
            body=None,
            headers={"X-Loop-Review-Token": adapter.token},
        )
        assert status == 400
        assert payload["error"] == "invalid request body length"

        status, payload = _request(f"{adapter.url}artifact/candidate")
        assert status == 404
        status, _ = _request(f"{adapter.url}artifact/base/openapi.yaml")
        assert status == 404

        status, payload = _request(
            f"{adapter.url}api/approve",
            method="POST",
            token=adapter.token,
            body={
                "binding": adapter.snapshot.binding.model_dump(mode="json"),
                "items": [],
                "handoff": [],
            },
        )
        assert status == 200
        assert payload["needs_follow_up"] is True
    finally:
        adapter.shutdown()
        thread.join(timeout=2)


def test_loopback_adapter_serves_base_artifacts_and_rejects_missing_candidate_file(tmp_path: Path) -> None:
    register.register_docset(
        tmp_path,
        Docset(docset_id="vendor-payments", title="Payments", provider="vendor", product="pay"),
    )
    workflow = ReviewWorkflow(tmp_path)
    first_run = write_run_dir(tmp_path / "output" / "20260723T120000.000000Z")
    first = workflow.open_review(ReviewRequest(docset_id="vendor-payments", run_dir=first_run))
    from datetime import datetime, timezone

    workflow.approve_review(
        first.key,
        ReviewDraft(binding=first.binding),
        now=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )
    second_run = write_run_dir(tmp_path / "output" / "20260724T120000.000000Z")
    snapshot = workflow.open_review(ReviewRequest(docset_id="vendor-payments", run_dir=second_run))
    adapter = ReviewWebAdapter(workflow, snapshot)
    thread = threading.Thread(target=adapter.serve_forever, daemon=True)
    thread.start()
    try:
        status, artifact = _request(f"{adapter.url}artifact/base/openapi.yaml")
        assert status == 200
        assert "openapi" in artifact

        candidate = paths.candidate_dir(tmp_path, "vendor-payments", second_run.name)
        (candidate / "integration-contract.json").unlink()
        status, _ = _request(f"{adapter.url}artifact/candidate/integration-contract.json")
        assert status == 404
    finally:
        adapter.shutdown()
        thread.join(timeout=2)
