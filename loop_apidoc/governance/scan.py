from __future__ import annotations

from loop_apidoc.freshness.models import BatchItemStatus, BatchReport
from loop_apidoc.governance.models import (
    GovernanceReport,
    GovernanceStatus,
    GovernanceTrigger,
    GovernanceTriggerKind,
)


def build_governance_report(scan: BatchReport) -> GovernanceReport:
    """Classify freshness findings into bounded, non-mutating review triggers."""
    triggers = [
        GovernanceTrigger(
            label=item.label,
            kind=(
                GovernanceTriggerKind.SOURCE_CHANGED
                if item.status is BatchItemStatus.CHANGED
                else GovernanceTriggerKind.FRESHNESS_INCONCLUSIVE
            ),
            reason=item.reason,
            run_dir=item.run_dir,
        )
        for item in scan.items
        if item.status in (BatchItemStatus.CHANGED, BatchItemStatus.INCONCLUSIVE, BatchItemStatus.ERROR)
    ]
    if any(trigger.kind is GovernanceTriggerKind.SOURCE_CHANGED for trigger in triggers):
        status = GovernanceStatus.REVIEW_REQUIRED
    elif triggers:
        status = GovernanceStatus.ATTENTION_REQUIRED
    else:
        status = GovernanceStatus.NO_ACTION
    return GovernanceReport(status=status, scanned_count=scan.total, triggers=triggers)
