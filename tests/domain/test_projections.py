from __future__ import annotations

import json

from loop_apidoc.domain.models import (
    ContractMetadata,
    Environment,
    EvidenceBinding,
    GroundedApiContract,
    Operation,
    Response,
)
from loop_apidoc.domain.projections import (
    OpenApiProjectionCompiler,
    ReviewProjectionCompiler,
)


def _contract() -> GroundedApiContract:
    return GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="contract-1",
            title="Health API",
            version="2026-07",
            source_set_id="sources",
            source_set_version="1",
            domain_version="1",
        ),
        environments=(
            Environment(name="production", servers=("https://api.example.com",)),
        ),
        operations=(
            Operation(
                method="GET",
                path="/health",
                responses=(Response(status_code="200", description="OK"),),
                evidence=(EvidenceBinding(fragment_id="fragment-1"),),
            ),
        ),
    )


def test_openapi_projection_is_reproducible():
    compiler = OpenApiProjectionCompiler(version="1")

    first = compiler.compile(_contract())
    second = compiler.compile(_contract())

    assert first == second
    assert first.media_type == "application/vnd.oai.openapi+json;version=3.1"
    payload = json.loads(first.content)
    assert payload["paths"]["/health"]["get"]["responses"]["200"]["description"] == "OK"


def test_review_projection_preserves_contract_states():
    projection = ReviewProjectionCompiler(version="1").compile(_contract())

    assert projection.name == "review-data"
    assert json.loads(projection.content)["metadata"]["contract_id"] == "contract-1"
