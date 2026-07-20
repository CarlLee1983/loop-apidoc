from __future__ import annotations

from collections.abc import Callable

from loop_apidoc.core.models import ExtractionWorkItem, RuntimeResult


class RuntimeContractError(ValueError):
    """A runtime result violates the typed work item contract."""


class CallableRuntimeAdapter:
    def __init__(
        self,
        runtime_identity: str,
        runtime_version: str,
        handler: Callable[[ExtractionWorkItem], RuntimeResult],
    ) -> None:
        self.runtime_identity = runtime_identity
        self.runtime_version = runtime_version
        self.handler = handler

    def propose(self, work_item: ExtractionWorkItem) -> RuntimeResult:
        result = self.handler(work_item)
        if (result.runtime_identity, result.runtime_version) != (
            self.runtime_identity,
            self.runtime_version,
        ):
            raise RuntimeContractError("runtime result identity/version mismatch")
        scope = set(work_item.evidence_scope)
        requested = set(work_item.requested_claim_kinds)
        for proposal in result.claim_proposals:
            if proposal.runtime_identity != self.runtime_identity:
                raise RuntimeContractError("claim proposal runtime identity mismatch")
            if proposal.claim_kind not in requested:
                raise RuntimeContractError("runtime returned an unrequested claim kind")
            outside = set(proposal.evidence_refs) - scope
            if outside:
                raise RuntimeContractError(
                    f"runtime referenced evidence outside authorized scope: {sorted(outside)}"
                )
        return result
