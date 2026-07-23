from __future__ import annotations

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.review import ReviewConflictError


def test_review_help_describes_local_candidate_workbench() -> None:
    result = CliRunner().invoke(app, ["review", "--help"])

    assert result.exit_code == 0
    assert "自動匯入候選" in result.output
    assert "--docset" in result.output
    assert "--run" in result.output


def test_review_starts_loopback_adapter_without_opening_a_browser(
    tmp_path, monkeypatch
) -> None:
    class FakeWorkflow:
        def __init__(self, _project):
            pass

        def open_review(self, _request):
            return object()

    class FakeAdapter:
        def __init__(self, _workflow, _snapshot, *, port: int):
            assert port == 0
            self.url = "http://127.0.0.1:45678/"
            self.served = False
            self.closed = False

        def serve_forever(self) -> None:
            self.served = True

        def shutdown(self) -> None:
            self.closed = True

    monkeypatch.setattr("loop_apidoc.review.ReviewWorkflow", FakeWorkflow)
    monkeypatch.setattr("loop_apidoc.review.web.ReviewWebAdapter", FakeAdapter)

    result = CliRunner().invoke(
        app, ["review", "--docset", "demo", "--run", str(tmp_path), "--no-open"]
    )

    assert result.exit_code == 0
    assert "http://127.0.0.1:45678/" in result.output


def test_review_reports_stale_evidence_as_input_error(tmp_path, monkeypatch) -> None:
    class ConflictingWorkflow:
        def __init__(self, _project):
            pass

        def open_review(self, _request):
            raise ReviewConflictError("saved review decision is stale")

    monkeypatch.setattr("loop_apidoc.review.ReviewWorkflow", ConflictingWorkflow)

    result = CliRunner().invoke(
        app, ["review", "--docset", "demo", "--run", str(tmp_path), "--no-open"]
    )

    assert result.exit_code == 2
    assert "review input error: saved review decision is stale" in result.output
