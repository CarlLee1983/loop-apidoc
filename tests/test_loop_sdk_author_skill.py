from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "loop-sdk-author"
VALIDATOR = SKILL_DIR / "scripts" / "validate_sdk_plan.py"


def test_loop_sdk_author_skill_is_deployable():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert text.startswith("---")
    assert "name: loop-sdk-author" in text
    assert "TODO" not in text
    assert "reference/sdk-plan-schema.md" in text
    assert "scripts/validate_sdk_plan.py" in text
    assert "openapi.yaml" in text
    assert "integration-contract.json" in text
    assert "handoff/sdk-hints.json" in text
    assert "app stack" in text


def test_sdk_plan_schema_reference_defines_boundaries():
    text = (SKILL_DIR / "reference" / "sdk-plan-schema.md").read_text(encoding="utf-8")

    assert "stack-neutral" in text
    assert "Do not copy OpenAPI schemas" in text
    assert "contract_pointer" in text
    assert "forbidden" in text.lower()


def test_validate_sdk_plan_accepts_minimal_stack_neutral_plan(tmp_path):
    plan = {
        "version": "1.0",
        "source_run_dir": "output/20260630T000000.000000Z",
        "contracts": {
            "openapi": "../openapi.yaml",
            "integration": "../integration-contract.json",
            "sdk_hints": "../handoff/sdk-hints.json",
        },
        "runtime": {
            "config": [
                {
                    "name": "base_url",
                    "source": "../openapi.yaml#/servers/0/url",
                    "required": True,
                }
            ]
        },
        "operation_groups": [{"name": "Payments", "operations": ["createPayment"]}],
        "operations": [
            {
                "operation_id": "createPayment",
                "method": "POST",
                "path": "/payments",
                "contract_pointer": "../openapi.yaml#/paths/~1payments/post",
                "sdk_method": "create_payment",
                "requires": ["runtime:base_url", "crypto:TradeInfo"],
                "gaps": [],
            }
        ],
        "mechanisms": {
            "auth": [],
            "crypto": [
                {
                    "name": "TradeInfo",
                    "contract_pointer": "../integration-contract.json#/crypto/0",
                    "purpose": "request",
                }
            ],
            "callbacks": [],
        },
        "adapters": [],
        "gaps": [],
    }
    path = tmp_path / "sdk-plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_validate_sdk_plan_rejects_app_stack_and_schema_copy(tmp_path):
    plan = {
        "version": "1.0",
        "source_run_dir": "output/run",
        "contracts": {
            "openapi": "../openapi.yaml",
            "integration": "../integration-contract.json",
            "sdk_hints": "../handoff/sdk-hints.json",
        },
        "runtime": {"config": []},
        "operation_groups": [],
        "operations": [
            {
                "operation_id": "createPayment",
                "method": "POST",
                "path": "/payments",
                "contract_pointer": "../openapi.yaml#/paths/~1payments/post",
                "sdk_method": "create_payment",
                "requestBody": {"properties": {"amount": {"type": "integer"}}},
            }
        ],
        "mechanisms": {"auth": [], "crypto": [], "callbacks": []},
        "framework": "Next.js",
        "adapters": [],
        "gaps": [],
    }
    path = tmp_path / "sdk-plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "framework" in result.stderr
    assert "requestBody" in result.stderr
