from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.core.governance import contract_digest
from loop_apidoc.domain.evidence import (
    ClaimEvidenceRelationship,
    EvidenceBundle,
    EvidenceFragment,
    FragmentPrecision,
    LineRangeLocator,
    SourceArtifact,
    SupportRelationshipType,
    VerificationMethod,
    fragment_digest,
)
from loop_apidoc.domain.models import (
    ClaimStatus,
    ContractClaim,
    ContractMetadata,
    EvidenceBinding,
    GroundedApiContract,
    Operation,
    Response,
)
from loop_apidoc.foundry import approve, feedback as foundry_feedback, importer, register
from loop_apidoc.foundry.models import Docset, FoundryPublicationError
from tests.foundry._fixtures import write_run_dir


runner = CliRunner()
_NOW = datetime(2026, 8, 2, 10, 0, 0, tzinfo=timezone.utc)
_RUN_ID = "20260802T100000.000000Z"
_CLAIM_ID = "operation:GET:/ping"


def _approved_contract(tmp_path: Path) -> tuple[str, GroundedApiContract]:
    register.register_docset(
        tmp_path,
        Docset(
            docset_id="demo-api",
            title="Demo API",
            provider="demo",
            product="backend",
        ),
    )
    excerpt = "GET /ping returns HTTP 200."
    fragment = EvidenceFragment(
        id="fragment-source-ping",
        source_artifact_id="artifact-manual",
        locator=LineRangeLocator(start_line=1, end_line=1),
        fragment_digest=fragment_digest(excerpt),
        normalized_excerpt=excerpt,
        semantic_value="200",
        semantic_role="response_status",
        precision=FragmentPrecision.EXACT,
    )
    relationship = ClaimEvidenceRelationship(
        id="relationship-ping-200",
        claim_identity=_CLAIM_ID,
        claim_path="/responses/200/status_code",
        fragment_id=fragment.id,
        relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
        verification_method=VerificationMethod.EXACT_NORMALIZED_VALUE,
        claim_value_digest="claim-value-ping-200",
        evidence_value_digest=fragment.fragment_digest,
        observed_value="200",
        reason_code="exact_match",
    )
    binding = EvidenceBinding(
        fragment_id=fragment.id,
        relationship_id=relationship.id,
        claim_identity=_CLAIM_ID,
        claim_path=relationship.claim_path,
        relationship=relationship.relationship,
        locator="manual.md:1",
    )
    response = Response(status_code="200", description="OK", evidence=(binding,))
    operation = Operation(method="GET", path="/ping", responses=(response,))
    contract = GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="demo-api",
            title="Demo API",
            version="1.0.0",
            source_set_id="demo-sources",
            source_set_version="1",
            domain_version="1",
        ),
        operations=(operation,),
        claims=(
            ContractClaim(
                identity=_CLAIM_ID,
                claim_kind="operation",
                status=ClaimStatus.SUPPORTED,
                value=operation.model_dump(mode="json", exclude={"evidence"}),
                evidence=(binding,),
            ),
        ),
    )
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    core_dir = run_dir / "core"
    core_dir.mkdir()
    (core_dir / "contract.json").write_text(
        contract.model_dump_json(indent=2), encoding="utf-8"
    )
    evidence = EvidenceBundle(
        source_set_id="demo-sources",
        source_set_version="1",
        artifacts=(
            SourceArtifact(
                id="artifact-manual",
                source_id="manual.md",
                media_type="text/markdown",
                content_digest="hash-manual",
                acquired_at=_NOW,
            ),
        ),
        fragments=(fragment,),
    )
    (core_dir / "evidence.json").write_text(
        evidence.model_dump_json(indent=2), encoding="utf-8"
    )
    (core_dir / "relationships.json").write_text(
        json.dumps([relationship.model_dump(mode="json")], indent=2),
        encoding="utf-8",
    )
    importer.import_run(tmp_path, "demo-api", run_dir)
    asset = approve.approve_candidate(
        tmp_path,
        "demo-api",
        _RUN_ID,
        approved_by="contract-reviewer",
        now=_NOW,
    )
    return asset.asset_id, contract


def _foundry_bytes(project: Path) -> dict[str, bytes]:
    root = project / ".foundry"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _bundle_payload(
    asset_id: str,
    contract: GroundedApiContract,
    *,
    observed: object = "200",
    outcome: str = "api_response",
) -> dict[str, object]:
    facts = [{"kind": "response_status", "value": observed}]
    facts_bytes = json.dumps(
        facts, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return {
        "schema_version": "implementation-observation-bundle/v1",
        "bundle_id": "bundle-ping-200",
        "base": {
            "docset_id": "demo-api",
            "asset_id": asset_id,
            "contract_digest": contract_digest(contract),
        },
        "policy_version": "conformance/v1",
        "redaction_policy_version": "redaction/v1",
        "producer": {"id": "integration-team", "version": "client/1.2.3"},
        "runner": {"id": "contract-suite", "version": "suite/1"},
        "applicability": {
            "provider": "demo",
            "product": "backend",
            "api_version": "1.0.0",
            "environment": "sandbox",
            "region": "tw",
            "endpoint_identity": "https://sandbox.example.test",
            "account_class": "merchant-test",
            "feature_flags": [],
            "authentication_role": "merchant",
            "client_version": "client/1.2.3",
            "harness_version": "suite/1",
            "test_data_class": "synthetic",
            "observed_from": "2026-08-02T09:59:00Z",
            "observed_until": "2026-08-02T10:00:00Z",
        },
        "observations": [
            {
                "id": "obs-ping-200",
                "kind": "response_status",
                "operation_ref": "GET /ping",
                "claim_identity": _CLAIM_ID,
                "claim_path": "/responses/200/status_code",
                "expected": "200",
                "probe_digest": "sha256:" + "1" * 64,
                "fixture_digest": "sha256:" + "2" * 64,
                "lineage": "independent",
                "replay": {
                    "executor": "contract-suite",
                    "steps": ["invoke GET /ping with synthetic fixture"],
                },
                "attempts": [
                    {
                        "id": "attempt-ping-1",
                        "observed_at": "2026-08-02T09:59:30Z",
                        "outcome": outcome,
                        "observed": observed,
                    }
                ],
                "evidence": [
                    {
                        "fragment_id": "fragment-ping-1",
                        "digest": "sha256:" + hashlib.sha256(facts_bytes).hexdigest(),
                        "media_type": "application/json",
                        "size_bytes": 18,
                        "sanitized_facts": facts,
                    }
                ],
            }
        ],
    }


def test_feedback_assess_confirms_observation_deterministically_without_governed_writes(
    tmp_path: Path,
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(
        json.dumps(_bundle_payload(asset_id, contract), indent=2),
        encoding="utf-8",
    )
    before = _foundry_bytes(tmp_path)
    first = tmp_path / "assessment-1"
    second = tmp_path / "assessment-2"

    result = runner.invoke(
        app,
        [
            "feedback",
            "assess",
            "--project",
            str(tmp_path),
            "--docset",
            "demo-api",
            "--asset",
            asset_id,
            "--bundle",
            str(bundle),
            "--output",
            str(first),
        ],
    )
    repeated = runner.invoke(
        app,
        [
            "feedback",
            "assess",
            "--project",
            str(tmp_path),
            "--docset",
            "demo-api",
            "--asset",
            asset_id,
            "--bundle",
            str(bundle),
            "--output",
            str(second),
        ],
    )

    assert result.exit_code == 0, result.output
    assert repeated.exit_code == 0, repeated.output
    report = json.loads((first / "feedback-assessment.json").read_text())
    assert report["relationships"][0]["relationship"] == "confirms"
    assert report["relationships"][0]["normative_value"] == "200"
    assert report["open_discrepancy_count"] == 0
    assert report["coverage"]["confirmed_claim_count"] == 1
    review = (first / "feedback-assessment.md").read_text()
    assert "# 實作回饋評估" in review
    assert "GET /ping returns HTTP 200." in review
    assert "fragment-source-ping" in review
    assert "fragment-ping-1" in review
    assert (first / "feedback-assessment.json").read_bytes() == (
        second / "feedback-assessment.json"
    ).read_bytes()
    assert _foundry_bytes(tmp_path) == before


def test_feedback_assessment_markdown_contains_complete_safe_review_context(
    tmp_path: Path,
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    payload = _bundle_payload(asset_id, contract)
    applicability = payload["applicability"]
    assert isinstance(applicability, dict)
    applicability["account_class"] = "operator-tier"
    applicability["feature_flags"] = ["new-checkout", "strict-status"]
    observations = payload["observations"]
    assert isinstance(observations, list)
    observation = observations[0]
    assert isinstance(observation, dict)
    observation["replay"] = {
        "executor": "contract-suite",
        "steps": [
            "prepare the synthetic fixture",
            "assert the response status",
        ],
    }
    attempts = observation["attempts"]
    assert isinstance(attempts, list)
    attempts.append(
        {
            "id": "attempt-ping-2",
            "observed_at": "2026-08-02T09:59:45Z",
            "outcome": "api_response",
            "observed": "200",
        }
    )
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    output = tmp_path / "assessment"

    result = runner.invoke(
        app,
        [
            "feedback",
            "assess",
            "--project",
            str(tmp_path),
            "--docset",
            "demo-api",
            "--asset",
            asset_id,
            "--bundle",
            str(bundle),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    review = (output / "feedback-assessment.md").read_text(encoding="utf-8")
    assert "## 適用範圍" in review
    for field in (
        "供應商",
        "產品",
        "API 版本",
        "環境",
        "區域",
        "端點識別",
        "帳戶類別",
        "功能旗標",
        "驗證角色",
        "用戶端版本",
        "測試框架版本",
        "測試資料類別",
        "觀測開始",
        "觀測結束",
    ):
        assert f"- {field}:" in review
    assert "產生者：`integration-team` / `client/1.2.3`" in review
    assert "執行者：`contract-suite` / `suite/1`" in review
    assert "探針摘要：`sha256:" in review
    assert "測試資料摘要：`sha256:" in review
    assert "觀測沿革：`independent`" in review
    assert "重播執行者：`contract-suite`" in review
    assert "1. `prepare the synthetic fixture`" in review
    assert "2. `assert the response status`" in review
    assert "attempt-ping-1" in review
    assert "api_response @ `2026-08-02T09:59:30+00:00`" in review
    assert "attempt-ping-2" in review
    assert "api_response @ `2026-08-02T09:59:45+00:00`" in review
    assert "規範片段：`fragment-source-ping`" in review
    assert "片段摘要：`" in review
    assert "定位資訊：`" in review
    assert "宣告：`operation:GET:/ping/responses/200/status_code`" in review
    assert "實作片段：`fragment-ping-1`" in review
    assert "媒體類型：`application/json`" in review
    assert "位元組數：`18`" in review
    assert "建議處置：`closed_no_change`" in review


@pytest.mark.parametrize(
    ("field", "raw_pii"),
    (
        ("account_class", "operator@example.test"),
        ("account_class", "SSN 123-45-6789"),
        ("endpoint_identity", "card 4111 1111 1111 1111"),
    ),
)
def test_feedback_assess_rejects_sensitive_bundle_before_writing_output(
    tmp_path: Path, field: str, raw_pii: str
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    payload = _bundle_payload(asset_id, contract)
    applicability = payload["applicability"]
    assert isinstance(applicability, dict)
    applicability[field] = raw_pii
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    output = tmp_path / "assessment"

    result = runner.invoke(
        app,
        [
            "feedback",
            "assess",
            "--project",
            str(tmp_path),
            "--docset",
            "demo-api",
            "--asset",
            asset_id,
            "--bundle",
            str(bundle),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2
    assert "PII" in result.output
    assert not output.exists()


def test_feedback_assess_reports_contradiction_for_review_without_patching_base(
    tmp_path: Path,
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(
        json.dumps(_bundle_payload(asset_id, contract, observed="201"), indent=2),
        encoding="utf-8",
    )
    before = _foundry_bytes(tmp_path)
    output = tmp_path / "assessment"

    result = runner.invoke(
        app,
        [
            "feedback",
            "assess",
            "--project",
            str(tmp_path),
            "--docset",
            "demo-api",
            "--asset",
            asset_id,
            "--bundle",
            str(bundle),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 1, result.output
    report = json.loads((output / "feedback-assessment.json").read_text())
    assert report["relationships"][0]["relationship"] == "contradicts"
    assert report["relationships"][0]["normative_value"] == "200"
    assert report["relationships"][0]["observed_value"] == "201"
    assert report["route"] == "amendment_proposal"
    assert report["open_discrepancy_count"] == 1
    assert _foundry_bytes(tmp_path) == before


def test_feedback_assess_refuses_output_inside_governed_foundry_state(
    tmp_path: Path,
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(
        json.dumps(_bundle_payload(asset_id, contract), indent=2), encoding="utf-8"
    )
    before = _foundry_bytes(tmp_path)
    output = tmp_path / ".foundry" / "assessment"

    result = runner.invoke(
        app,
        [
            "feedback",
            "assess",
            "--project",
            str(tmp_path),
            "--docset",
            "demo-api",
            "--asset",
            asset_id,
            "--bundle",
            str(bundle),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2, result.output
    assert "outside .foundry" in result.output
    assert not output.exists()
    assert _foundry_bytes(tmp_path) == before


def test_feedback_assess_rejects_path_traversal_identifiers(tmp_path: Path) -> None:
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text("{}", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "feedback", "assess", "--project", str(tmp_path), "--docset", "../demo-api",
            "--asset", "asset", "--bundle", str(bundle), "--output",
            str(tmp_path / "assessment"),
        ],
    )

    assert result.exit_code == 2, result.output
    assert "unsafe docset id" in result.output


def test_feedback_assess_rejects_base_without_complete_normative_evidence(
    tmp_path: Path,
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    evidence_path = (
        tmp_path
        / ".foundry"
        / "api"
        / "docsets"
        / "demo-api"
        / "assets"
        / asset_id
        / "artifacts"
        / "core"
        / "evidence.json"
    )
    evidence_path.unlink()
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(
        json.dumps(_bundle_payload(asset_id, contract), indent=2), encoding="utf-8"
    )
    output = tmp_path / "assessment"

    result = runner.invoke(
        app,
        [
            "feedback",
            "assess",
            "--project",
            str(tmp_path),
            "--docset",
            "demo-api",
            "--asset",
            asset_id,
            "--bundle",
            str(bundle),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2, result.output
    assert "evidence" in result.output.lower()
    assert not output.exists()


def test_feedback_assess_rejects_secret_fields_without_echoing_values(
    tmp_path: Path,
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    payload = _bundle_payload(asset_id, contract)
    observations = payload["observations"]
    assert isinstance(observations, list)
    observation = observations[0]
    assert isinstance(observation, dict)
    observation["Authorization"] = "Bearer super-secret-value"
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    output = tmp_path / "assessment"

    result = runner.invoke(
        app,
        [
            "feedback",
            "assess",
            "--project",
            str(tmp_path),
            "--docset",
            "demo-api",
            "--asset",
            asset_id,
            "--bundle",
            str(bundle),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2, result.output
    assert "super-secret-value" not in result.output
    assert not output.exists()


def test_feedback_assess_requires_digest_bound_sanitized_evidence_facts(
    tmp_path: Path,
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    payload = _bundle_payload(asset_id, contract)
    observations = payload["observations"]
    assert isinstance(observations, list)
    observation = observations[0]
    assert isinstance(observation, dict)
    evidence = observation["evidence"]
    assert isinstance(evidence, list)
    fragment = evidence[0]
    assert isinstance(fragment, dict)
    fragment.pop("sanitized_facts")
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    output = tmp_path / "assessment"

    result = runner.invoke(
        app,
        [
            "feedback",
            "assess",
            "--project",
            str(tmp_path),
            "--docset",
            "demo-api",
            "--asset",
            asset_id,
            "--bundle",
            str(bundle),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2, result.output
    assert "observation bundle is invalid" in result.output
    assert not output.exists()


def test_feedback_propose_submit_approve_compose_and_current_exact_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset_id, contract = _approved_contract(tmp_path)
    bundle = tmp_path / "feedback-bundle.json"
    bundle.write_text(
        json.dumps(_bundle_payload(asset_id, contract, observed="201"), indent=2),
        encoding="utf-8",
    )
    assessment_dir = tmp_path / "assessment"
    assessed = runner.invoke(
        app,
        [
            "feedback", "assess", "--project", str(tmp_path), "--docset", "demo-api",
            "--asset", asset_id, "--bundle", str(bundle), "--output", str(assessment_dir),
        ],
    )
    assert assessed.exit_code == 1, assessed.output

    proposals_dir = tmp_path / "proposals"
    proposed = runner.invoke(
        app,
        [
            "feedback", "propose", "--assessment",
            str(assessment_dir / "feedback-assessment.json"), "--at",
            "2026-08-02T10:05:00Z", "--output", str(proposals_dir),
        ],
    )
    assert proposed.exit_code == 0, proposed.output
    assert "# 相容性修訂提案" in (
        proposals_dir / "amendment-proposals.md"
    ).read_text(encoding="utf-8")
    proposal_files = list(proposals_dir.glob("proposal-*.json"))
    assert len(proposal_files) == 1

    submitted = runner.invoke(
        app,
        [
            "feedback", "submit", "--project", str(tmp_path), "--docset", "demo-api",
            "--bundle", str(bundle), "--assessment",
            str(assessment_dir / "feedback-assessment.json"), "--proposal",
            str(proposal_files[0]),
        ],
    )
    assert submitted.exit_code == 0, submitted.output
    assessment = json.loads(
        (assessment_dir / "feedback-assessment.json").read_text(encoding="utf-8")
    )
    case_id = assessment["assessment_id"]
    normative_current = (
        tmp_path / ".foundry/api/docsets/demo-api/current.json"
    ).read_bytes()

    approve_args = [
        "feedback", "approve", "--project", str(tmp_path), "--docset", "demo-api",
        "--case", case_id, "--approved-by", "human-reviewer", "--approver-version", "1",
        "--at", "2026-08-02T10:10:00Z", "--expires-at", "2026-09-01T10:10:00Z",
        "--rationale", "Sandbox compatibility exception.",
    ]
    original_approve = foundry_feedback.approve_feedback_case

    def fail_publication(*_args: object, **_kwargs: object) -> None:
        raise FoundryPublicationError("injected publication failure")

    monkeypatch.setattr(foundry_feedback, "approve_feedback_case", fail_publication)
    failed = runner.invoke(app, approve_args)
    assert failed.exit_code == 2, failed.output
    assert "feedback approve error: injected publication failure" in failed.output

    monkeypatch.setattr(
        foundry_feedback, "approve_feedback_case", original_approve
    )
    approved = runner.invoke(app, approve_args)
    assert approved.exit_code == 0, approved.output
    assert (
        tmp_path / ".foundry/api/docsets/demo-api/current.json"
    ).read_bytes() == normative_current

    target = tmp_path / "target.json"
    target.write_text(
        json.dumps(_bundle_payload(asset_id, contract)["applicability"], indent=2),
        encoding="utf-8",
    )
    current = runner.invoke(
        app,
        [
            "feedback", "current", "--project", str(tmp_path), "--docset", "demo-api",
            "--target", str(target), "--at", "2026-08-02T10:11:00Z",
        ],
    )
    assert current.exit_code == 0, current.output
    current_payload = json.loads(current.output)
    assert current_payload["target"]["environment"] == "sandbox"
    assert current_payload["base_asset_id"] == asset_id
    assert current_payload["stale_amendment_count"] == 0
    assert "unresolved_contradiction_count" in current_payload

    case_dir = (
        tmp_path / ".foundry/api/docsets/demo-api/feedback/cases" / case_id
    )
    composed_dir = tmp_path / "composed"
    composed = runner.invoke(
        app,
        [
            "feedback", "compose", "--project", str(tmp_path), "--docset", "demo-api",
            "--asset", asset_id, "--target", str(target), "--amendment",
            str(case_dir / "approved-amendment.json"), "--at", "2026-08-02T10:11:00Z",
            "--output", str(composed_dir),
        ],
    )
    assert composed.exit_code == 1, composed.output
    assert "# 有效契約組合" in (
        composed_dir / "effective-contract.md"
    ).read_text(encoding="utf-8")
    effective = json.loads((composed_dir / "effective-contract.json").read_text())
    assert len(effective["applied_amendment_ids"]) == 1
    assert effective["untested_material_claim_count"] > 0
    assert effective["open_discrepancy_count"] > 0
