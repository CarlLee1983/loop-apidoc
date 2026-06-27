from __future__ import annotations

from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.validate.completeness import check_completeness
from loop_apidoc.validate.consistency import check_consistency
from loop_apidoc.validate.coverage import check_manifest_coverage
from loop_apidoc.validate.integration import check_integration
from loop_apidoc.validate.models import ValidationReport
from loop_apidoc.validate.speculation import check_speculation
from loop_apidoc.validate.structure import check_structure


def validate_outputs(
    plan: NormalizationPlan, result: GenerateResult, manifest: Manifest
) -> ValidationReport:
    """Aggregate the §9 validation categories plus §6 manifest coverage.
    Pure; the correction loop reuses this seam.

    Manifest coverage surfaces local sources that could not be incorporated
    into normalization: UNREADABLE sources as errors, UNSUPPORTED sources as
    warnings (see check_manifest_coverage).
    """
    issues = []
    issues += check_structure(result.openapi, result.markdown)
    issues += check_completeness(plan)
    issues += check_consistency(result.openapi, result.markdown)
    issues += check_speculation(result.openapi, result.provenance)
    issues += check_manifest_coverage(manifest)
    issues += check_integration(plan, result)
    return ValidationReport(issues=issues)
