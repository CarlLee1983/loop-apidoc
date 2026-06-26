from __future__ import annotations

from pathlib import Path

import yaml

from loop_apidoc.generate.markdown import build_markdown
from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.generate.openapi import build_openapi
from loop_apidoc.generate.provenance import build_provenance
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan


def build_result(plan: NormalizationPlan, manifest: Manifest) -> GenerateResult:
    return GenerateResult(
        openapi=build_openapi(plan),
        markdown=build_markdown(plan, manifest),
        provenance=build_provenance(plan),
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
    return result
