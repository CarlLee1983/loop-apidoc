from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from loop_apidoc.generate.models import GenerateResult, ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport
from loop_apidoc.validate.validator import validate_outputs


def _single(code: IssueCode, location: str, evidence: str, fix: str) -> ValidationReport:
    return ValidationReport(issues=[Issue(
        code=code, severity=Severity.ERROR, location=location,
        evidence=evidence, suggested_fix=fix)])


def validate_run_dir(run_dir: Path) -> ValidationReport:
    openapi_path = run_dir / "openapi.yaml"
    markdown_path = run_dir / "api-guide.zh-TW.md"
    provenance_path = run_dir / "provenance.json"
    plan_path = run_dir / "plan" / "normalization-plan.json"
    manifest_path = run_dir / "manifest.json"

    for required in (openapi_path, markdown_path, provenance_path, plan_path, manifest_path):
        if not required.exists():
            return _single(IssueCode.OUTPUT_MISMATCH, required.name,
                           f"run directory 缺少 {required.name}", "重新執行生成步驟")

    try:
        openapi = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return _single(IssueCode.OPENAPI_INVALID, "openapi.yaml",
                       f"openapi.yaml 無法解析：{str(exc)[:200]}", "修正 YAML 格式")
    if not isinstance(openapi, dict):
        return _single(IssueCode.OPENAPI_INVALID, "openapi.yaml",
                       "openapi.yaml 不是物件", "重新生成 openapi.yaml")

    try:
        provenance = ProvenanceDocument.model_validate_json(
            provenance_path.read_text(encoding="utf-8"))
        plan = NormalizationPlan.model_validate_json(
            plan_path.read_text(encoding="utf-8"))
        manifest = Manifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        return _single(IssueCode.OUTPUT_MISMATCH, "json-artifact",
                       f"JSON artifact schema 不符：{str(exc)[:200]}", "重新生成該 artifact")

    markdown = markdown_path.read_text(encoding="utf-8")
    result = GenerateResult(openapi=openapi, markdown=markdown, provenance=provenance)
    return validate_outputs(plan, result, manifest)
