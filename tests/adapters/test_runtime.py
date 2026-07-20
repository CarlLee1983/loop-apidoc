from __future__ import annotations

import pytest

from loop_apidoc.adapters.runtime import CallableRuntimeAdapter, RuntimeContractError
from loop_apidoc.core.models import ClaimProposal, ExtractionWorkItem, RuntimeResult


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
