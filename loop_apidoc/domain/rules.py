from __future__ import annotations

from pydantic import ConfigDict

from loop_apidoc.domain.claim_paths import material_claim_paths
from loop_apidoc.domain.evidence import SupportRelationshipType
from loop_apidoc.domain.identity import (
    DomainIdentityError,
    canonical_operation_identity,
)
from loop_apidoc.domain.models import ClaimStatus, FrozenModel, GroundedApiContract


class DomainFinding(FrozenModel):
    code: str
    message: str
    location: str
    claim_identity: str | None = None
    evidence_scope: tuple[str, ...] = ()
    default_severity: str = "error"
    root_cause: str | None = None


class ApiDomainRulePack(FrozenModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: str

    def evaluate(self, contract: GroundedApiContract) -> tuple[DomainFinding, ...]:
        findings: list[DomainFinding] = []
        schema_names = {schema.name for schema in contract.schemas}
        security_names = {scheme.name for scheme in contract.security}
        environment_names = {environment.name for environment in contract.environments}
        operation_ids: set[str] = set()

        for index, operation in enumerate(contract.operations):
            location = f"operations[{index}]"
            try:
                identity = canonical_operation_identity(
                    operation.method, operation.path
                )
            except DomainIdentityError as exc:
                findings.append(
                    _finding("OPERATION_IDENTITY_INVALID", str(exc), location)
                )
                identity = location
            if identity in operation_ids:
                findings.append(
                    _finding(
                        "OPERATION_IDENTITY_DUPLICATE", identity, location, identity
                    )
                )
            operation_ids.add(identity)
            if not operation.responses:
                findings.append(
                    _finding(
                        "RESPONSE_REQUIRED",
                        "operation has no response",
                        location,
                        identity,
                    )
                )
            if not operation.evidence:
                findings.append(
                    _finding(
                        "OPERATION_EVIDENCE_REQUIRED",
                        "operation has no evidence binding",
                        location,
                        identity,
                    )
                )
            if operation.server and operation.server not in environment_names:
                findings.append(
                    _finding(
                        "SERVER_REFERENCE_UNRESOLVED",
                        operation.server,
                        location,
                        operation.server,
                    )
                )
            refs = [operation.request_schema_ref]
            refs.extend(parameter.schema_ref for parameter in operation.parameters)
            refs.extend(response.schema_ref for response in operation.responses)
            for ref in sorted({ref for ref in refs if ref}):
                if ref not in schema_names:
                    findings.append(
                        _finding(
                            "SCHEMA_REFERENCE_UNRESOLVED",
                            ref,
                            location,
                            f"schema:{ref}",
                        )
                    )
            for ref in operation.security:
                if ref not in security_names:
                    findings.append(
                        _finding(
                            "SECURITY_REFERENCE_UNRESOLVED",
                            ref,
                            location,
                            f"security:{ref}",
                        )
                    )

        for index, schema in enumerate(contract.schemas):
            for field in schema.fields:
                if field.schema_ref and field.schema_ref not in schema_names:
                    findings.append(
                        _finding(
                            "SCHEMA_REFERENCE_UNRESOLVED",
                            field.schema_ref,
                            f"schemas[{index}].fields.{field.name}",
                            f"schema:{field.schema_ref}",
                        )
                    )
                if (
                    field.required
                    and field.condition is not None
                    and not field.condition.strip()
                ):
                    findings.append(
                        _finding(
                            "CONDITIONAL_REQUIREDNESS_INCOMPLETE",
                            field.name,
                            f"schemas[{index}].fields.{field.name}",
                        )
                    )

        for index, webhook in enumerate(contract.webhooks):
            if not webhook.verification or not webhook.expected_response:
                findings.append(
                    _finding(
                        "CALLBACK_VERIFICATION_INCOMPLETE",
                        webhook.name,
                        f"webhooks[{index}]",
                    )
                )

        for index, mechanic in enumerate(contract.integration_mechanics):
            if (
                mechanic.kind in {"crypto", "encryption", "signature"}
                and not mechanic.steps
            ):
                findings.append(
                    _finding(
                        "CRYPTOGRAPHIC_CHAIN_INCOMPLETE",
                        mechanic.name,
                        f"integration_mechanics[{index}]",
                    )
                )
            for ref in mechanic.operation_refs:
                if ref not in operation_ids:
                    findings.append(
                        _finding(
                            "INTEGRATION_REFERENCE_UNRESOLVED",
                            ref,
                            f"integration_mechanics[{index}]",
                            ref,
                        )
                    )

        for index, error in enumerate(contract.errors):
            for ref in error.applicable_to:
                if ref not in operation_ids:
                    findings.append(
                        _finding(
                            "ERROR_APPLICABILITY_UNRESOLVED",
                            ref,
                            f"errors[{index}]",
                            ref,
                        )
                    )

        for index, claim in enumerate(contract.claims):
            location = f"claims[{index}]"
            if claim.status in {ClaimStatus.SUPPORTED, ClaimStatus.WAIVED} and not (
                claim.evidence
            ):
                findings.append(
                    _finding(
                        "CLAIM_EVIDENCE_REQUIRED",
                        claim.identity,
                        location,
                        claim.identity,
                    )
                )
            semantic = tuple(
                binding
                for binding in claim.evidence
                if binding.relationship_id is not None
                and binding.relationship
                in {
                    SupportRelationshipType.EXPLICIT_SUPPORT,
                    SupportRelationshipType.DERIVED_SUPPORT,
                }
            )
            if claim.status in {ClaimStatus.SUPPORTED, ClaimStatus.WAIVED}:
                if not semantic:
                    findings.append(
                        _finding(
                            "CLAIM_SEMANTIC_SUPPORT_REQUIRED",
                            claim.identity,
                            location,
                            claim.identity,
                        )
                    )
                elif claim.claim_kind is not None:
                    required = set(
                        material_claim_paths(claim.claim_kind, claim.value)
                    )
                    covered = {
                        binding.claim_path
                        for binding in semantic
                        if binding.claim_path is not None
                    }
                    if required - covered:
                        findings.append(
                            _finding(
                                "CLAIM_SUPPORT_COVERAGE_INCOMPLETE",
                                claim.identity,
                                location,
                                claim.identity,
                            )
                        )
            if any(
                binding.relationship is SupportRelationshipType.CONTRADICTS
                for binding in claim.evidence
            ):
                findings.append(
                    _finding(
                        "CLAIM_EVIDENCE_CONTRADICTS",
                        claim.identity,
                        location,
                        claim.identity,
                    )
                )
        return tuple(
            sorted(findings, key=lambda item: (item.location, item.code, item.message))
        )


def _finding(
    code: str,
    message: str,
    location: str,
    root_cause: str | None = None,
) -> DomainFinding:
    return DomainFinding(
        code=code,
        message=message,
        location=location,
        root_cause=root_cause,
    )
