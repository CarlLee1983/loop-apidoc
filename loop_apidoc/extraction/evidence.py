"""Versioned exact-evidence references accepted from agent extraction JSON.

The agent-native compatibility boundary keeps legacy ``source`` strings for
the shipping generators.  This model is the parallel, claim-level contract
used when an agent can name an exact source fragment.  It deliberately stores
the digest asserted by the agent: the read-side evidence verifier materializes
the same locator from the manifest source and compares it before assembly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from loop_apidoc.domain.evidence import (
    FragmentLocator,
    UnresolvedLocator,
    WholeDocumentLocator,
)
from loop_apidoc.domain.models import FrozenModel


class ExtractionEvidenceReference(FrozenModel):
    """One v1 claim-path binding to an exact source fragment.

    ``source`` is an exact manifest identity (a local relative path or an
    acquired URL), not a legacy free-form citation.  ``claim_path`` uses the
    Canonical API Contract material-claim path syntax, for example
    ``/summary`` or ``/responses/200/description``.
    """

    version: Literal[1]
    source: str
    locator: FragmentLocator
    fragment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_path: str

    @field_validator("source")
    @classmethod
    def source_is_exact_and_nonblank(cls, value: str) -> str:
        if value != value.strip() or not value:
            raise ValueError("must be a non-blank, unpadded manifest source identity")
        return value

    @field_validator("claim_path")
    @classmethod
    def claim_path_is_canonical_shape(cls, value: str) -> str:
        if value != value.strip() or not value.startswith("/"):
            raise ValueError("must be an unpadded material claim path starting with '/'")
        return value

    @model_validator(mode="after")
    def locator_is_exact(self) -> ExtractionEvidenceReference:
        if isinstance(self.locator, (WholeDocumentLocator, UnresolvedLocator)):
            raise ValueError("exact evidence requires a typed, non-document locator")
        return self
