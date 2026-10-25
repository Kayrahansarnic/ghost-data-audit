"""Turn policy decisions into the ordered FINDING / REMEDIATION / VERIFICATION steps."""
from __future__ import annotations

from .policy import Decision

FIND_ORDER = ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK"]
REME_ORDER = ["DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD"]
VERI_ORDER = ["VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED",
              "VERIFY_RECORD_ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED"]
STATE = {
    "REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT", "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
    "REPORT_RESTORE_RISK": "ACTIVE", "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED",
    "DELETE_RECORD": "ABSENT", "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT", "VERIFY_RECORD_REDACTED": "REDACTED",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
    "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}


def build_steps(decisions: list[Decision], status: str) -> list[dict]:
    items: list[tuple] = []  # (phase_rank, op_rank, system, resource, phase, op, evidence)
    incomplete = status == "INCOMPLETE"
    for d in decisions:
        sysid, rid = d.key
        if d.finding:
            items.append((0, FIND_ORDER.index(d.finding), sysid, rid, "FINDING", d.finding, d.cite))
        if d.remediation:
            items.append((1, REME_ORDER.index(d.remediation), sysid, rid, "REMEDIATION", d.remediation, ""))
        ev = "" if incomplete else d.cite
        items.append((2, VERI_ORDER.index(d.verification), sysid, rid, "VERIFICATION", d.verification, ev))
    items.sort(key=lambda x: x[:4])
    return [
        {"step_no": i, "phase": ph, "system_id": s, "resource_id": r, "operation": op,
         "state": STATE[op], "evidence_id": ev}
        for i, (_, _, s, r, ph, op, ev) in enumerate(items, 1)
    ]
