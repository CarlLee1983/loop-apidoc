from __future__ import annotations

import pytest

from loop_apidoc.adapters.runtime import CallableRuntimeAdapter, RuntimeContractError
from loop_apidoc.core.models import (
    ClaimProposal,
    ClaimSupportProposal,
    ExtractionWorkItem,
    RuntimeResult,
)
from loop_apidoc.domain.evidence import (
    SupportRelationshipType,
    VerificationMethod,
)


def test_runtime_adapter_rejects_out_of_scope_evidence():
    def handler(work_item):
        return RuntimeResult(
            claim_proposals=(
                ClaimProposal(
                    id="p1",
                    claim_kind="operation",
                    subject="GET /health",
                    predicate="exists",
                    value=True,
                    evidence_refs=("fragment-outside",),
                    runtime_identity="parser",
                ),
            ),
            runtime_identity="parser",
            runtime_version="1",
        )

    adapter = CallableRuntimeAdapter("parser", "1", handler)
    work_item = ExtractionWorkItem(
        task_id="task-1",
        evidence_scope=("fragment-1",),
        requested_claim_kinds=("operation",),
        output_schema="claim-proposal/v1",
        correlation_id="correlation-1",
    )

    with pytest.raises(RuntimeContractError, match="outside"):
        adapter.propose(work_item)


def test_runtime_adapter_rejects_out_of_scope_support_proposal():
    def handler(work_item):
        return RuntimeResult(
            claim_proposals=(
                ClaimProposal(
                    id="p1",
                    claim_kind="operation",
                    subject="GET /health",
                    predicate="exists",
                    value=True,
                    support_proposals=(
                        ClaimSupportProposal(
                            fragment_id="fragment-outside",
                            claim_path="",
                            proposed_relationship=(
                                SupportRelationshipType.EXPLICIT_SUPPORT
                            ),
                            verification_method=(
                                VerificationMethod.EXACT_NORMALIZED_VALUE
                            ),
                        ),
                    ),
                    runtime_identity="parser",
                ),
            ),
            runtime_identity="parser",
            runtime_version="1",
        )

    adapter = CallableRuntimeAdapter("parser", "1", handler)
    work_item = ExtractionWorkItem(
        task_id="task-1",
        evidence_scope=("fragment-1",),
        requested_claim_kinds=("operation",),
        output_schema="claim-proposal/v2",
        correlation_id="correlation-1",
    )

    with pytest.raises(RuntimeContractError, match="outside"):
        adapter.propose(work_item)
