from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from loop_apidoc.domain.base import FrozenModel


class ProviderErratumMetadata(FrozenModel):
    schema_version: Literal["provider-erratum/v1"]
    erratum_id: str = Field(min_length=1, max_length=240)
    docset_id: str = Field(min_length=1, max_length=200)
    base_asset_id: str = Field(min_length=1, max_length=240)
    provider: str = Field(min_length=1, max_length=200)
    product: str = Field(min_length=1, max_length=200)
    artifact_name: str = Field(min_length=1, max_length=240)
    artifact_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    issued_at: datetime

    @field_validator("issued_at")
    @classmethod
    def _timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("erratum issue time must include a timezone")
        return value

    @field_validator("artifact_name")
    @classmethod
    def _plain_filename_required(cls, value: str) -> str:
        if "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError("erratum artifact_name must be a plain filename")
        return value


class ErratumPipelineStep(FrozenModel):
    order: int = Field(ge=1)
    stage: str
    action: str


class ProviderErratumHandoff(FrozenModel):
    schema_version: Literal["provider-erratum-handoff/v1"] = (
        "provider-erratum-handoff/v1"
    )
    erratum: ProviderErratumMetadata
    verified_artifact_digest: str
    source_role: Literal["supplemental"] = "supplemental"
    mutates_normative_contract: Literal[False] = False
    publishes_effective_contract: Literal[False] = False
    pipeline: tuple[ErratumPipelineStep, ...]


def build_provider_erratum_handoff(
    metadata: ProviderErratumMetadata, verified_artifact_digest: str
) -> ProviderErratumHandoff:
    steps = (
        ErratumPipelineStep(
            order=1,
            stage="register_supplemental_source",
            action="Register the verified local erratum as a supplemental supplier source.",
        ),
        ErratumPipelineStep(
            order=2,
            stage="acquire_and_preprocess",
            action="Copy or normalize it into a new immutable readable source package.",
        ),
        ErratumPipelineStep(
            order=3,
            stage="inspect_source_risk",
            action="Build the package manifest and run inspect-source-risk before agent reading.",
        ),
        ErratumPipelineStep(
            order=4,
            stage="assess_source_quality",
            action="Perform agent quality review and run assess-sources with the risk report.",
        ),
        ErratumPipelineStep(
            order=5,
            stage="extract_and_assemble",
            action="Extract against all supplier sources, verify extraction, and assemble a candidate.",
        ),
        ErratumPipelineStep(
            order=6,
            stage="review_and_approve_normative_release",
            action="Human-review, import, and approve a new immutable Normative Contract release.",
        ),
        ErratumPipelineStep(
            order=7,
            stage="reassess_feedback",
            action="Re-run passive observations against the newly approved normative base.",
        ),
    )
    return ProviderErratumHandoff(
        erratum=metadata,
        verified_artifact_digest=verified_artifact_digest,
        pipeline=steps,
    )
