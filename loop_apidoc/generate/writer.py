from __future__ import annotations

from pathlib import Path

import yaml

from loop_apidoc.generate.examples import build_examples
from loop_apidoc.generate.integration import build_integration_document
from loop_apidoc.generate.markdown import build_markdown
from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.generate.openapi import build_openapi
from loop_apidoc.generate.provenance import build_provenance
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan


def build_result(plan: NormalizationPlan, manifest: Manifest) -> GenerateResult:
    openapi = build_openapi(plan)
    return GenerateResult(
        openapi=openapi,
        markdown=build_markdown(plan, manifest),
        provenance=build_provenance(plan),
        integration=build_integration_document(plan),
        examples=build_examples(openapi, plan),
    )


def generate_outputs(
    plan: NormalizationPlan, manifest: Manifest, run_dir: Path
) -> GenerateResult:
    result = build_result(plan, manifest)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "openapi.yaml").write_text(
        yaml.safe_dump(result.openapi, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (run_dir / "api-guide.zh-TW.md").write_text(result.markdown, encoding="utf-8")
    (run_dir / "provenance.json").write_text(
        result.provenance.model_dump_json(indent=2), encoding="utf-8"
    )
    if result.integration is not None:
        import json

        (run_dir / "integration-contract.json").write_text(
            json.dumps(result.integration, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    for relpath, content in result.examples.items():
        target = run_dir / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return result
