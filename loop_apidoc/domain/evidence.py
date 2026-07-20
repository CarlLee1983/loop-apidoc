from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Mapping

from pydantic import Field, model_validator

from loop_apidoc.domain.base import FrozenModel


class WholeDocumentLocator(FrozenModel):
    kind: Literal["whole_document"] = "whole_document"


class PageLocator(FrozenModel):
    kind: Literal["page"] = "page"
    page: int = Field(ge=1)


class LineRangeLocator(FrozenModel):
    kind: Literal["line_range"] = "line_range"
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @model_validator(mode="after")
    def end_is_not_before_start(self) -> LineRangeLocator:
        if self.end_line < self.start_line:
            raise ValueError("line range end must not be before start")
        return self


class SectionLocator(FrozenModel):
    kind: Literal["section"] = "section"
    heading_path: tuple[str, ...] = ()
    anchor: str | None = None


class TableLocator(FrozenModel):
    kind: Literal["table"] = "table"
    table_index: int = Field(ge=0)
    heading_path: tuple[str, ...] = ()


class TableCellLocator(FrozenModel):
    kind: Literal["table_cell"] = "table_cell"
    table_index: int = Field(ge=0)
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    row_key: str | None = None
    column_name: str | None = None


class JsonPointerLocator(FrozenModel):
    kind: Literal["json_pointer"] = "json_pointer"
    pointer: str


class CssSelectorLocator(FrozenModel):
    kind: Literal["css_selector"] = "css_selector"
    selector: str


class XPathLocator(FrozenModel):
    kind: Literal["xpath"] = "xpath"
    expression: str


class UnresolvedLocator(FrozenModel):
    kind: Literal["unresolved"] = "unresolved"
    raw: str | None = None
    reason: str


FragmentLocator = Annotated[
    WholeDocumentLocator
    | PageLocator
    | LineRangeLocator
    | SectionLocator
    | TableLocator
    | TableCellLocator
    | JsonPointerLocator
    | CssSelectorLocator
    | XPathLocator
    | UnresolvedLocator,
    Field(discriminator="kind"),
]


class FragmentPrecision(str, Enum):
    EXACT = "exact"
    DOCUMENT = "document"
    UNRESOLVED = "unresolved"


class FragmentReconstructionRef(FrozenModel):
    source_artifact_id: str
    locator: FragmentLocator
    expected_digest: str | None = None


class TransformationStep(FrozenModel):
    name: str
    version: str
    input_digest: str
    output_digest: str


class DerivationStep(FrozenModel):
    name: str
    version: str
    input_digests: tuple[str, ...]
    output_digest: str


class SourceDescriptor(FrozenModel):
    id: str
    kind: str
    locator: str
    media_type: str | None = None


class SourceSet(FrozenModel):
    id: str
    version: str
    sources: tuple[SourceDescriptor, ...]
    lineage: tuple[str, ...] = ()


class SourceArtifact(FrozenModel):
    id: str
    source_id: str
    media_type: str
    content_digest: str
    acquired_at: datetime
    acquisition_metadata: tuple[tuple[str, str], ...] = ()


class EvidenceFragment(FrozenModel):
    id: str
    source_artifact_id: str
    locator: FragmentLocator
    fragment_digest: str
    normalized_excerpt: str | None = None
    reconstruction_ref: FragmentReconstructionRef | None = None
    semantic_value: Any = None
    semantic_role: str | None = None
    parent_fragment_id: str | None = None
    precision: FragmentPrecision = FragmentPrecision.DOCUMENT
    transformation: tuple[TransformationStep, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_locator(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        locator = normalized.get("locator")
        if locator == "whole":
            normalized["locator"] = {"kind": "whole_document"}
            normalized.setdefault("precision", FragmentPrecision.DOCUMENT)
        elif isinstance(locator, str):
            normalized["locator"] = {
                "kind": "unresolved",
                "raw": locator,
                "reason": "legacy string locator",
            }
            normalized.setdefault("precision", FragmentPrecision.UNRESOLVED)
        return normalized

    @model_validator(mode="after")
    def exact_content_is_reconstructable(self) -> EvidenceFragment:
        if self.precision is FragmentPrecision.EXACT:
            if isinstance(self.locator, (WholeDocumentLocator, UnresolvedLocator)):
                raise ValueError("exact fragment requires an exact locator")
            if self.normalized_excerpt is None and self.reconstruction_ref is None:
                raise ValueError(
                    "exact fragment requires excerpt or reconstruction reference"
                )
        return self


class EvidenceBundle(FrozenModel):
    source_set_id: str
    source_set_version: str
    artifacts: tuple[SourceArtifact, ...]
    fragments: tuple[EvidenceFragment, ...]


class SupportRelationshipType(str, Enum):
    EXPLICIT_SUPPORT = "explicit_support"
    DERIVED_SUPPORT = "derived_support"
    CONTRADICTS = "contradicts"
    INSUFFICIENT = "insufficient"


class VerificationMethod(str, Enum):
    EXACT_NORMALIZED_VALUE = "exact_normalized_value"
    TABLE_CELL_MAPPING = "table_cell_mapping"
    STRUCTURED_FIELD_PATH = "structured_field_path"
    ENUM_VALUE = "enum_value"
    SOURCE_FACT_COVERAGE = "source_fact_coverage"


class ClaimSupportProposal(FrozenModel):
    fragment_id: str
    claim_path: str
    proposed_relationship: SupportRelationshipType
    verification_method: VerificationMethod
    derivation_steps: tuple[DerivationStep, ...] = ()
    runtime_observation: str | None = None

    @model_validator(mode="after")
    def runtime_can_only_propose_support(self) -> ClaimSupportProposal:
        allowed = {
            SupportRelationshipType.EXPLICIT_SUPPORT,
            SupportRelationshipType.DERIVED_SUPPORT,
        }
        if self.proposed_relationship not in allowed:
            raise ValueError("runtime may only propose explicit or derived support")
        return self


class ClaimEvidenceRelationship(FrozenModel):
    id: str
    claim_identity: str
    claim_path: str
    fragment_id: str
    relationship: SupportRelationshipType
    verification_method: VerificationMethod
    claim_value_digest: str
    evidence_value_digest: str | None = None
    observed_value: Any = None
    reason_code: str
    derivation_steps: tuple[DerivationStep, ...] = ()


def normalize_excerpt(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    while lines and not lines[0].strip(" \t"):
        lines.pop(0)
    while lines and not lines[-1].strip(" \t"):
        lines.pop()
    return "\n".join(lines)


def _jsonable(value: Any) -> Any:
    if isinstance(value, FrozenModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def fragment_digest(normalized_fragment: str) -> str:
    return hashlib.sha256(normalized_fragment.encode("utf-8")).hexdigest()


def make_fragment_id(
    *,
    source_artifact_id: str,
    locator: FragmentLocator,
    fragment_digest: str,
    parent_fragment_id: str | None = None,
) -> str:
    payload = {
        "source_artifact_id": source_artifact_id,
        "locator": locator,
        "fragment_digest": fragment_digest,
        "parent_fragment_id": parent_fragment_id,
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:24]
    return f"fragment-{digest}"


def make_relationship_id(
    relationship: ClaimEvidenceRelationship | Mapping[str, Any],
) -> str:
    if isinstance(relationship, ClaimEvidenceRelationship):
        payload = relationship.model_dump(mode="json", exclude={"id"}, exclude_none=True)
    else:
        payload = {key: value for key, value in relationship.items() if key != "id"}
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:24]
    return f"relationship-{digest}"
