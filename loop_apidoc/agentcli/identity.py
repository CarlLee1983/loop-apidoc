"""Backward-compatible re-exports for extraction operation identities.

New consumers should import from :mod:`loop_apidoc.operation_identity`, which
does not depend on the agent CLI adapter.
"""

from loop_apidoc.operation_identity import (
    endpoint_identity,
    entries,
    extraction_identities,
    normalized_summary,
)

__all__ = (
    "endpoint_identity",
    "entries",
    "extraction_identities",
    "normalized_summary",
)
