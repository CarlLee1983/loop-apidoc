from __future__ import annotations

import html
import json
import shutil
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ValidationError
import yaml

from loop_apidoc.domain.evidence import (
    FragmentPrecision,
    SupportRelationshipType,
    fragment_digest,
    normalize_excerpt,
)
from loop_apidoc.domain.models import (
    AsyncApiTransportBinding,
    EvidenceBinding,
    GraphqlTransportBinding,
)
from loop_apidoc.domain.projections import (
    AsyncApiProjectionCompiler,
    GraphqlProjectionCompiler,
    ProjectionInput,
    ProvenanceProjectionCompiler,
    ReviewProjectionCompiler,
    UnsupportedProjectionError,
)
from loop_apidoc.domain.rules import ApiDomainRulePack, DomainFinding
from loop_apidoc.protocol_run.models import (
    ContractFormat,
    ProtocolRunInputError,
    ProtocolRunResult,
)
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport
from loop_apidoc.validate.report import write_reports


_COMPILER_VERSION = "1"
_SUPPORTED_RELATIONSHIPS = {
    SupportRelationshipType.EXPLICIT_SUPPORT,
    SupportRelationshipType.DERIVED_SUPPORT,
}
_BINDING_CLAIM_PREFIX = "/binding/"


def load_projection_input(path: Path) -> ProjectionInput:
    try:
        value = ProjectionInput.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise ProtocolRunInputError(f"cannot read projection input {path}: {exc}") from exc
    if value.source_set is None or value.evidence is None:
        raise ProtocolRunInputError(
            "projection input requires contract, source_set, and evidence"
        )
    return value


def project_contract(
    projection_input: ProjectionInput,
    *,
    contract_format: ContractFormat,
    output: Path,
    generated_at: datetime | None = None,
) -> ProtocolRunResult:
    if output.exists():
        raise ProtocolRunInputError(f"output run directory already exists: {output}")
    _require_format_contract(projection_input, contract_format)
    compiler = _compiler(contract_format)
    try:
        spec = compiler.compile(projection_input)
        provenance = ProvenanceProjectionCompiler(_COMPILER_VERSION).compile(
            projection_input
        )
        review_data = ReviewProjectionCompiler(_COMPILER_VERSION).compile(
            projection_input
        )
    except UnsupportedProjectionError as exc:
        raise ProtocolRunInputError(str(exc)) from exc

    report = _validate_projection_input(projection_input, contract_format, spec.content)
    status = "passed" if report.ok else "failed"
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.", dir=str(output.parent))
    )
    try:
        _write_run(
            staging,
            projection_input=projection_input,
            contract_format=contract_format,
            spec_content=spec.content,
            provenance_content=provenance.content,
            review_content=review_data.content,
            report=report,
            status=status,
            generated_at=generated_at or datetime.now(timezone.utc),
        )
        staging.replace(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return ProtocolRunResult(
        format=contract_format,
        status=status,
        run_dir=str(output),
        report=report,
    )


def _compiler(contract_format: ContractFormat):
    if contract_format is ContractFormat.GRAPHQL:
        return GraphqlProjectionCompiler(_COMPILER_VERSION)
    return AsyncApiProjectionCompiler(_COMPILER_VERSION)


def _require_format_contract(
    projection_input: ProjectionInput,
    contract_format: ContractFormat,
) -> None:
    contract = projection_input.contract
    if contract.operations:
        raise ProtocolRunInputError(
            "project-contract accepts protocol-neutral interactions, not legacy operations"
        )
    if not contract.interactions:
        raise ProtocolRunInputError("contract contains no interactions")
    expected = (
        GraphqlTransportBinding
        if contract_format is ContractFormat.GRAPHQL
        else AsyncApiTransportBinding
    )
    unsupported = sorted(
        {
            interaction.binding.transport
            for interaction in contract.interactions
            if not isinstance(interaction.binding, expected)
        }
    )
    if unsupported:
        raise ProtocolRunInputError(
            f"{contract_format.value} projection does not support transports: "
            + ", ".join(unsupported)
        )


def _validate_projection_input(
    projection_input: ProjectionInput,
    contract_format: ContractFormat,
    spec_content: bytes,
) -> ValidationReport:
    issues = _identity_issues(projection_input)
    issues.extend(_grounding_issues(projection_input))
    issues.extend(_claim_value_issues(projection_input))
    issues.extend(_coverage_issues(projection_input, contract_format))
    issues.extend(
        _domain_issue(finding)
        for finding in ApiDomainRulePack(version="1").evaluate(
            projection_input.contract
        )
    )
    issues.extend(
        _structural_issues(
            contract_format,
            spec_content,
            projection_input=projection_input,
        )
    )
    return ValidationReport(
        issues=sorted(
            issues,
            key=lambda issue: (issue.severity.value, issue.location, issue.code.value),
        )
    )


def _identity_issues(projection_input: ProjectionInput) -> list[Issue]:
    source_set = projection_input.source_set
    evidence = projection_input.evidence
    assert source_set is not None and evidence is not None
    metadata = projection_input.contract.metadata
    expected = (source_set.id, source_set.version)
    actual = (metadata.source_set_id, metadata.source_set_version)
    bundle = (evidence.source_set_id, evidence.source_set_version)
    issues: list[Issue] = []
    if actual != expected or bundle != expected:
        issues.append(
            Issue(
                code=IssueCode.SOURCE_UNVERIFIED,
                severity=Severity.ERROR,
                location="projection-input.source_set",
                evidence=(
                    f"contract={actual!r}, source_set={expected!r}, evidence={bundle!r}"
                ),
                suggested_fix="Use one exact source-set identity and version across the input.",
            )
        )
    return issues


def _grounding_issues(projection_input: ProjectionInput) -> list[Issue]:
    source_set = projection_input.source_set
    evidence = projection_input.evidence
    assert source_set is not None and evidence is not None
    source_ids = {source.id for source in source_set.sources}
    artifacts = {artifact.id: artifact for artifact in evidence.artifacts}
    fragments = {fragment.id: fragment for fragment in evidence.fragments}
    issues: list[Issue] = []
    for artifact in evidence.artifacts:
        if artifact.source_id not in source_ids:
            issues.append(
                _unverified(
                    f"evidence.artifacts.{artifact.id}",
                    f"source {artifact.source_id!r} is absent from source_set",
                )
            )
    for fragment in evidence.fragments:
        if fragment.source_artifact_id not in artifacts:
            issues.append(
                _unverified(
                    f"evidence.fragments.{fragment.id}",
                    f"artifact {fragment.source_artifact_id!r} is absent",
                )
            )
        if fragment.precision is FragmentPrecision.EXACT:
            if fragment.normalized_excerpt is None:
                issues.append(
                    _unverified(
                        f"evidence.fragments.{fragment.id}",
                        "standalone protocol runs require an embedded exact excerpt",
                    )
                )
            elif fragment_digest(normalize_excerpt(fragment.normalized_excerpt)) != (
                fragment.fragment_digest
            ):
                issues.append(
                    _unverified(
                        f"evidence.fragments.{fragment.id}",
                        "exact fragment digest does not match its normalized excerpt",
                    )
                )
    for index, binding in enumerate(_evidence_bindings(projection_input.contract)):
        fragment = fragments.get(binding.fragment_id)
        location = f"contract.evidence[{index}]"
        if (
            binding.relationship_id is None
            or binding.claim_identity is None
            or binding.claim_path is None
            or binding.relationship not in _SUPPORTED_RELATIONSHIPS
        ):
            issues.append(
                _unverified(location, "binding lacks a supported semantic relationship")
            )
        elif fragment is None:
            issues.append(
                _unverified(location, f"fragment {binding.fragment_id!r} is absent")
            )
        elif fragment.precision is not FragmentPrecision.EXACT:
            issues.append(
                _unverified(location, f"fragment {binding.fragment_id!r} is not exact")
            )
    return issues


def _claim_value_issues(projection_input: ProjectionInput) -> list[Issue]:
    """Compare every emitted binding value against the fragment it cites.

    `_grounding_issues` only proves a citation is well-formed and exact. Without
    this check a contract may name any fragment for any value, so support would
    be by reference rather than by value.
    """
    evidence = projection_input.evidence
    assert evidence is not None
    fragments = {fragment.id: fragment for fragment in evidence.fragments}
    issues: list[Issue] = []
    # One claim path may legitimately be cited more than once; a given
    # (path, fragment) contradiction is still a single defect to fix.
    reported: set[tuple[str, str]] = set()
    for index, interaction in enumerate(projection_input.contract.interactions):
        binding = interaction.binding
        for reference in (*interaction.evidence, *binding.evidence):
            claim_path = reference.claim_path
            if claim_path is None or not claim_path.startswith(_BINDING_CLAIM_PREFIX):
                continue
            if reference.relationship not in _SUPPORTED_RELATIONSHIPS:
                continue
            fragment = fragments.get(reference.fragment_id)
            if fragment is None or fragment.precision is not FragmentPrecision.EXACT:
                continue
            attribute = claim_path[len(_BINDING_CLAIM_PREFIX):]
            location = f"interactions[{index}]{claim_path}"
            if (location, fragment.id) in reported:
                continue
            reported.add((location, fragment.id))
            if "/" in attribute or not hasattr(binding, attribute):
                issues.append(
                    _unverified(
                        location,
                        f"claim path {claim_path!r} does not resolve on the binding",
                    )
                )
                continue
            claimed = _claim_text(getattr(binding, attribute))
            if claimed is None:
                continue
            stated = fragment.semantic_value or fragment.normalized_excerpt
            if stated is None:
                continue
            if normalize_excerpt(claimed) != normalize_excerpt(str(stated)):
                issues.append(
                    _unverified(
                        location,
                        f"emitted value {claimed!r} contradicts exact fragment "
                        f"{fragment.id} stating {stated!r}",
                    )
                )
    return issues


def _claim_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, str):
        return value
    return None


def _coverage_issues(
    projection_input: ProjectionInput,
    contract_format: ContractFormat,
) -> list[Issue]:
    evidence = projection_input.evidence
    assert evidence is not None
    fragments = {fragment.id: fragment for fragment in evidence.fragments}

    def supported_paths(bindings: tuple[EvidenceBinding, ...]) -> set[str]:
        return {
            binding.claim_path
            for binding in bindings
            if binding.claim_path is not None
            and binding.relationship_id is not None
            and binding.relationship in _SUPPORTED_RELATIONSHIPS
            and binding.fragment_id in fragments
            and fragments[binding.fragment_id].precision is FragmentPrecision.EXACT
        }

    issues: list[Issue] = []
    for index, interaction in enumerate(projection_input.contract.interactions):
        binding = interaction.binding
        covered = supported_paths((*interaction.evidence, *binding.evidence))
        required = (
            {
                "/binding/operation_kind",
                "/binding/root_field",
                "/binding/output_schema_ref",
                *(
                    {"/binding/output_required"}
                    if binding.output_required is not None
                    else set()
                ),
            }
            if contract_format is ContractFormat.GRAPHQL
            else {
                "/binding/channel",
                "/binding/channel_address",
                "/binding/direction",
                "/binding/message_name",
                "/binding/payload_schema_ref",
            }
        )
        for claim_path in sorted(required - covered):
            issues.append(
                _unverified(
                    f"interactions[{index}]{claim_path}",
                    f"emitted {contract_format.value} value has no exact support",
                )
            )

    for schema_index, schema in enumerate(projection_input.contract.schemas):
        covered = supported_paths(
            (*schema.evidence, *(binding for field in schema.fields for binding in field.evidence))
        )
        for field in schema.fields:
            prefix = f"/fields/{field.name}"
            if not any(path == prefix or path.startswith(f"{prefix}/") for path in covered):
                issues.append(
                    _unverified(
                        f"schemas[{schema_index}].fields.{field.name}",
                        f"emitted schema field {schema.name}.{field.name} has no exact support",
                    )
                )
    return issues


def _evidence_bindings(value: object) -> tuple[EvidenceBinding, ...]:
    found: dict[tuple, EvidenceBinding] = {}

    def visit(item: object) -> None:
        if isinstance(item, EvidenceBinding):
            found[
                (
                    item.relationship_id,
                    item.fragment_id,
                    item.claim_identity,
                    item.claim_path,
                )
            ] = item
        elif isinstance(item, BaseModel):
            for name in type(item).model_fields:
                visit(getattr(item, name))
        elif isinstance(item, tuple | list):
            for child in item:
                visit(child)

    visit(value)
    return tuple(
        found[key]
        for key in sorted(
            found,
            key=lambda item: tuple(part or "" for part in item),
        )
    )


def _unverified(location: str, evidence: str) -> Issue:
    return Issue(
        code=IssueCode.SOURCE_UNVERIFIED,
        severity=Severity.ERROR,
        location=location,
        evidence=evidence,
        suggested_fix="Bind the claim to a supported exact fragment from the declared source set.",
    )


def _domain_issue(finding: DomainFinding) -> Issue:
    if "EVIDENCE" in finding.code:
        code = IssueCode.SOURCE_UNVERIFIED
    elif "CONTRADICT" in finding.code:
        code = IssueCode.SOURCE_CONFLICT
    elif "REQUIRED" in finding.code or "UNRESOLVED" in finding.code:
        code = IssueCode.REQUIRED_INFO_MISSING
    else:
        code = IssueCode.UNSUPPORTED_ASSERTION
    return Issue(
        code=code,
        severity=Severity.ERROR,
        location=finding.location,
        evidence=f"{finding.code}: {finding.message}",
        suggested_fix="Correct the canonical contract from source-backed evidence.",
    )


def _structural_issues(
    contract_format: ContractFormat,
    content: bytes,
    *,
    projection_input: ProjectionInput,
) -> list[Issue]:
    text = content.decode("utf-8")
    valid = bool(text.strip())
    if contract_format is ContractFormat.GRAPHQL:
        valid = (
            valid
            and text.count("{") == text.count("}")
            and all(schema.fields for schema in projection_input.contract.schemas)
        )
    else:
        valid = valid and _asyncapi_document_is_valid(text)
    if valid:
        return []
    return [
        Issue(
            code=IssueCode.OUTPUT_MISMATCH,
            severity=Severity.ERROR,
            location=_spec_filename(contract_format),
            evidence=f"generated {contract_format.value} artifact is structurally invalid",
            suggested_fix="Correct the source-backed contract and regenerate the artifact.",
        )
    ]


def _asyncapi_document_is_valid(text: str) -> bool:
    """Parse the emitted AsyncAPI document and check it hangs together.

    A prefix test on the serialized text is not a structural check: `asyncapi`
    sorts first among the emitted keys, so it holds for every document this
    compiler can produce.
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    if not isinstance(document, dict):
        return False
    if not isinstance(document.get("asyncapi"), str):
        return False
    channels = document.get("channels")
    operations = document.get("operations")
    if not isinstance(channels, dict) or not channels:
        return False
    if not isinstance(operations, dict) or not operations:
        return False
    schemas = (document.get("components") or {}).get("schemas")
    if not isinstance(schemas, dict):
        return False
    for operation in operations.values():
        target = _ref_name(operation.get("channel"), "#/channels/")
        if target is None or target not in channels:
            return False
    for channel in channels.values():
        messages = channel.get("messages")
        if not isinstance(messages, dict) or not messages:
            return False
        for message in messages.values():
            name = _ref_name(
                message.get("payload"), "#/components/schemas/"
            )
            if name is None or name not in schemas:
                return False
            if not (schemas[name] or {}).get("properties"):
                return False
    return True


def _ref_name(value: object, prefix: str) -> str | None:
    if not isinstance(value, dict):
        return None
    ref = value.get("$ref")
    if not isinstance(ref, str) or not ref.startswith(prefix):
        return None
    return ref[len(prefix):]


def _write_run(
    output: Path,
    *,
    projection_input: ProjectionInput,
    contract_format: ContractFormat,
    spec_content: bytes,
    provenance_content: bytes,
    review_content: bytes,
    report: ValidationReport,
    status: str,
    generated_at: datetime,
) -> None:
    (output / _spec_filename(contract_format)).write_bytes(spec_content)
    guide_name = f"{contract_format.value}-guide.zh-TW.md"
    (output / guide_name).write_text(
        _render_guide(projection_input, contract_format), encoding="utf-8"
    )
    (output / "provenance.json").write_bytes(provenance_content)
    (output / "review.html").write_text(
        _render_review_html(
            review_content,
            contract_format,
            status,
            report=report,
        ),
        encoding="utf-8",
    )
    write_reports(report, output / "validation")
    (output / "run.json").write_text(
        json.dumps(
            {
                "format": contract_format.value,
                "status": status,
                "generated_at": generated_at.isoformat(),
                "projection_versions": {
                    contract_format.value: _COMPILER_VERSION,
                    "provenance": _COMPILER_VERSION,
                    "review-data": _COMPILER_VERSION,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _spec_filename(contract_format: ContractFormat) -> str:
    return "schema.graphql" if contract_format is ContractFormat.GRAPHQL else "asyncapi.yaml"


def _render_guide(
    projection_input: ProjectionInput,
    contract_format: ContractFormat,
) -> str:
    contract = projection_input.contract
    lines = [
        f"# {contract.metadata.title} — {contract_format.value} 整合指南",
        "",
        f"- 契約版本：`{contract.metadata.version or '來源未提供'}`",
        f"- 來源集：`{contract.metadata.source_set_id}@{contract.metadata.source_set_version}`",
        "",
        "## 互動",
        "",
    ]
    for interaction in contract.interactions:
        binding = interaction.binding
        if isinstance(binding, GraphqlTransportBinding):
            detail = f"{binding.operation_kind.value} `{binding.root_field}`"
        else:
            detail = (
                f"{binding.direction.value} `{binding.channel}`"
                f"（address：`{binding.channel_address}`）"
            )
        lines.append(f"- {detail}")
    if contract.gaps:
        lines.extend(["", "## 已知缺口", ""])
        lines.extend(f"- `{gap.identity}`：{gap.reason}" for gap in contract.gaps)
    return "\n".join(lines).rstrip() + "\n"


def _render_review_html(
    review_content: bytes,
    contract_format: ContractFormat,
    status: str,
    *,
    report: ValidationReport,
) -> str:
    payload = json.loads(review_content)
    pretty = html.escape(json.dumps(payload, ensure_ascii=False, indent=2))
    validation = html.escape(report.model_dump_json(indent=2))
    return (
        "<!doctype html>\n<meta charset=\"utf-8\">\n"
        f"<title>{contract_format.value} contract review</title>\n"
        f"<h1>{contract_format.value} contract review</h1>\n"
        f"<p>Validation: <strong>{status.upper()}</strong></p>\n"
        f"<h2>Contract and evidence</h2>\n<pre>{pretty}</pre>\n"
        f"<h2>Validation report</h2>\n<pre>{validation}</pre>\n"
    )
