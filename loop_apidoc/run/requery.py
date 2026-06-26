from __future__ import annotations

from loop_apidoc.run.correction import actionable_codes, classify_issue
from loop_apidoc.run.models import CorrectionCategory
from loop_apidoc.validate.models import ValidationReport


def stages_for_requery(report: ValidationReport) -> set[str]:
    """Map actionable RE_QUERY issues to the extraction stages that produced them.

    Coarse mapping (spec deferral #3): endpoint-shaped issues bundle stages 05
    (inventory) and 06 (details); security issues map to stage 04. Mapping is by
    Issue.location prefix only. An empty result means the locations could not be
    pinned to a stage — the caller falls back to a full re-extraction.
    """
    stages: set[str] = set()
    for issue in actionable_codes(report):
        if classify_issue(issue) is not CorrectionCategory.RE_QUERY:
            continue
        location = issue.location
        if location.startswith("components.securitySchemes"):
            stages.add("04")
        elif location.startswith("paths.") or location.startswith("endpoints["):
            stages.update({"05", "06"})
    return stages
