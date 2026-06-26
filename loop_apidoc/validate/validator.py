from __future__ import annotations

from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.validate.completeness import check_completeness
from loop_apidoc.validate.consistency import check_consistency
from loop_apidoc.validate.models import ValidationReport
from loop_apidoc.validate.speculation import check_speculation
from loop_apidoc.validate.structure import check_structure


def validate_outputs(
    plan: NormalizationPlan, result: GenerateResult, manifest: Manifest
) -> ValidationReport:
    """Aggregate the four §9 validation categories. Pure; Plan 6 reuses this seam.

    `manifest` is reserved for Plan 6's §6 manifest-coverage deepening.
    """
    issues = []
    issues += check_structure(result.openapi, result.markdown)
    issues += check_completeness(plan)
    issues += check_consistency(result.openapi, result.markdown)
    issues += check_speculation(result.openapi, result.provenance)
    return ValidationReport(issues=issues)
