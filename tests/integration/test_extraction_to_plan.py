from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.extraction.orchestrator import run_extraction
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.plan.models import NormalizationPlan, PlanItemStatus

NB = "https://notebooklm.google.com/notebook/abc"

# stage_id -> answer text; structured stages return a complete json block.
_ANSWERS = {
    "03": '```json\n{"environments": [{"name": "prod", "base_url": "https://api", '
          '"version": "v1", "source": "api.pdf"}], "missing": []}\n```',
    "04": '```json\n{"security_schemes": [{"name": "ApiKey", "type": "apiKey", '
          '"location": "header", "details": "X-Key", "source": "api.pdf"}], '
          '"missing": []}\n```',
    "05": '```json\n{"endpoints": [{"method": "GET", "path": "/u", "summary": "list", '
          '"source": "api.pdf"}], "missing": []}\n```',
    "06": '```json\n{"endpoint_details": [{"method": "GET", "path": "/u", '
          '"parameters": [{"name": "page"}], "request": null, "responses": '
          '[{"status": "200"}], "examples": [], "source": "api.pdf"}], "missing": []}\n```',
    "07": '```json\n{"schemas": [{"name": "User", "fields": [{"name": "id"}], '
          '"enums": [], "constraints": null, "source": "api.pdf"}], "missing": []}\n```',
    "08": '```json\n{"errors": [{"code": "E1", "meaning": "bad", "http_status": "400", '
          '"source": "api.pdf"}], "missing": []}\n```',
    "09": '```json\n{"operational": [{"topic": "rate limit", "detail": "100/m", '
          '"source": "api.pdf"}], "missing": []}\n```',
}


class _Result:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.returncode = 0


# The current stage's json_hint contains `MUST be `<key>`` (backtick-wrapped); the
# double-quote form `"<key>"` also appears in earlier answers embedded via
# build_known_summary, so match on the backtick form which is unique to the active stage.
_KEY_TO_STAGE = {
    "`environments`": "03", "`security_schemes`": "04", "`endpoints`": "05",
    "`endpoint_details`": "06", "`schemas`": "07", "`errors`": "08", "`operational`": "09",
}


class _Adapter:
    def ask(self, question: str, notebook_url: str) -> _Result:
        for token, stage_id in _KEY_TO_STAGE.items():
            if token in question:
                return _Result(_ANSWERS[stage_id])
        return _Result("Prose answer; the sources cover the basics.")


def _manifest() -> Manifest:
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return Manifest(
        sources_root="/src", generated_at=now,
        local_sources=[
            LocalSource(relative_path="api.pdf", mime_type="application/pdf",
                        source_format=SourceFormat.PDF, size_bytes=1, sha256="x",
                        scanned_at=now, supported=True, status=ProcessingStatus.PENDING),
        ],
    )


def test_end_to_end_extraction_and_plan(tmp_path: Path):
    run_dir = tmp_path / "run-1"
    extraction_dir = run_dir / "extraction"
    plan_dir = run_dir / "plan"
    plan_dir.mkdir(parents=True)

    store = ExtractionStore(extraction_dir)
    extraction = run_extraction(_Adapter(), NB, store)

    # extraction artifacts on disk
    assert (extraction_dir / "queries.jsonl").exists()
    assert (extraction_dir / "answers" / "05-initial.txt").exists()
    jsonl = (extraction_dir / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(jsonl) == len(extraction.artifacts)
    assert all(json.loads(line)["answer_path"].startswith("answers/") for line in jsonl)

    plan = build_normalization_plan(extraction, _manifest())
    plan_path = plan_dir / "normalization-plan.json"
    plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    # reload and assert source-grounded structure
    restored = NormalizationPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    # stage 05 endpoint and stage 06 details merge into ONE endpoint, not two
    assert len(restored.endpoints) == 1
    assert restored.endpoints[0].path == "/u"
    assert restored.endpoints[0].status is PlanItemStatus.SUPPORTED
    assert restored.endpoints[0].parameters == [{"name": "page"}]
    assert restored.endpoints[0].responses == [{"status": "200"}]
    assert restored.security_schemes[0].name == "ApiKey"
    assert restored.errors[0].code == "E1"
    assert restored.environments[0].base_url == "https://api"
    # narrative notes preserved
    assert restored.overview_note
    # everything is source-grounded -> no unverified items
    assert restored.unverified_items == []


def test_no_credentials_in_artifacts(tmp_path: Path):
    store = ExtractionStore(tmp_path / "extraction")
    run_extraction(_Adapter(), NB, store)
    blob = (tmp_path / "extraction" / "queries.jsonl").read_text(encoding="utf-8")
    for secret in ("cookie", "browser state", "credential"):
        assert secret.lower() not in blob.lower()
