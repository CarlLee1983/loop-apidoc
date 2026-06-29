from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from loop_apidoc.agentcli.assemble import run_assemble_pipeline

_CASE = Path(__file__).resolve().parents[2] / "benchmarks" / "adyen-payments-multimethod"
_FIXED_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_adyen_payments_post_body_has_native_oneof(tmp_path):
    if not (_CASE / "sources").is_dir():
        pytest.skip("adyen sources/ not present (operator-provided, gitignored)")
    result = run_assemble_pipeline(
        sources_root=_CASE / "sources",
        extraction_dir=_CASE / "extraction",
        output_root=tmp_path,
        run_id="bench",
        generated_at=_FIXED_TS,
    )
    doc = yaml.safe_load((Path(result.run_dir) / "openapi.yaml").read_text("utf-8"))
    body = doc["paths"]["/payments"]["post"]["requestBody"]["content"][
        "application/json"]["schema"]
    pm = body["properties"]["paymentMethod"]
    refs = {m["$ref"] for m in pm["oneOf"]}
    assert refs == {
        "#/components/schemas/CardDetails",
        "#/components/schemas/IdealDetails",
        "#/components/schemas/ApplePayDetails",
    }
    assert pm["discriminator"]["propertyName"] == "type"
