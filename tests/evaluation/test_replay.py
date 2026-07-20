from __future__ import annotations

import inspect

from loop_apidoc.adapters.runtime import CallableRuntimeAdapter
from loop_apidoc.core.models import ClaimProposal, ExtractionWorkItem, RuntimeResult
from loop_apidoc.domain.rules import ApiDomainRulePack
from loop_apidoc.evaluation.models import EvaluationCase, ExpectedClaim
from loop_apidoc.evaluation.replay import ReplayRunner


def test_replay_runner_has_no_production_mutation_ports():
    assert set(inspect.signature(ReplayRunner).parameters) == {"runtime", "domain_pack"}


def test_replay_is_reproducible_for_fixed_runtime_result():
    result = RuntimeResult(
        claim_proposals=(
            ClaimProposal(
                id="p1",
                claim_kind="operation",
                subject="GET /health",
                predicate="exists",
                value=True,
                evidence_refs=("fragment-1",),
                runtime_identity="parser",
            ),
        ),
        runtime_identity="parser",
        runtime_version="1",
    )
    runtime = CallableRuntimeAdapter("parser", "1", lambda _: result)
    case = EvaluationCase(
        id="case-1",
        version="1",
        work_item=ExtractionWorkItem(
            task_id="task",
            evidence_scope=("fragment-1",),
            requested_claim_kinds=("operation",),
            output_schema="claim-proposal/v1",
            correlation_id="correlation",
        ),
        expected_claims=(
            ExpectedClaim(
                identity="claim:operation:GET /health:exists",
                value=True,
                evidence_refs=("fragment-1",),
            ),
        ),
    )
    runner = ReplayRunner(runtime=runtime, domain_pack=ApiDomainRulePack(version="1"))

    assert runner.run(case) == runner.run(case)
    assert runner.run(case).metrics.claim_recall == 1.0
