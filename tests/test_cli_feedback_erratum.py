from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.test_cli_feedback import (
    _approved_contract,
    _bundle_payload,
    app,
    runner,
)

def test_feedback_provider_erratum_verifies_local_artifact_and_only_writes_handoff(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "erratum.pdf"
    artifact.write_bytes(b"formal provider erratum")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    metadata = tmp_path / "erratum.json"
    metadata.write_text(
        json.dumps(
            {
                "schema_version": "provider-erratum/v1",
                "erratum_id": "erratum-2026-08",
                "docset_id": "demo-api",
                "base_asset_id": "demo-api-base",
                "provider": "demo",
                "product": "backend",
                "artifact_name": "erratum.pdf",
                "artifact_digest": f"sha256:{digest}",
                "issued_at": "2026-08-02T10:00:00Z",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "erratum-handoff"

    result = runner.invoke(
        app,
        [
            "feedback", "provider-erratum", "--metadata", str(metadata),
            "--artifact", str(artifact), "--output", str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads((output / "provider-erratum-handoff.json").read_text())
    assert report["verified_artifact_digest"] == f"sha256:{digest}"
    assert [item["stage"] for item in report["pipeline"]][:3] == [
        "register_supplemental_source", "acquire_and_preprocess", "inspect_source_risk"
    ]
    assert not (tmp_path / ".foundry").exists()


def test_feedback_propose_returns_one_when_assessment_needs_no_amendment(
    tmp_path: Path,
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(
        json.dumps(_bundle_payload(asset_id, contract), indent=2), encoding="utf-8"
    )
    assessment_dir = tmp_path / "assessment"
    assessed = runner.invoke(
        app,
        [
            "feedback", "assess", "--project", str(tmp_path), "--docset", "demo-api",
            "--asset", asset_id, "--bundle", str(bundle), "--output", str(assessment_dir),
        ],
    )
    assert assessed.exit_code == 0, assessed.output

    output = tmp_path / "proposals"
    result = runner.invoke(
        app,
        [
            "feedback", "propose", "--assessment",
            str(assessment_dir / "feedback-assessment.json"), "--at",
            "2026-08-02T10:05:00Z", "--output", str(output),
        ],
    )

    assert result.exit_code == 1, result.output
    assert json.loads((output / "amendment-proposals.json").read_text()) == []
