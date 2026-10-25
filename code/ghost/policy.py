"""Apply deletion_rules.csv to a reconstructed resource state."""
from __future__ import annotations

from dataclasses import dataclass

from .evidence import model as M
from .evidence.loader import is_direct
from .evidence.model import Rec


@dataclass
class Decision:
    key: tuple
    rec: Rec
    finding: str | None      # operation name or None when compliant
    remediation: str | None
    verification: str
    cite: str = ""


def decide(rec: Rec, cite: str = "") -> Decision | None:
    d = _decide(rec)
    if d:
        d.cite = cite
    return d


def _decide(rec: Rec) -> Decision | None:
    t = rec.rtype
    if t in (M.PROFILE, M.SEARCH, M.EXPORT, M.MARKETING, M.ATTACHMENT, M.CONTACT, M.OBJECT):
        bad = rec.present
        return Decision(rec.key, rec, "REPORT_REMAINING_RECORD" if bad else None,
                        "DELETE_RECORD" if bad else None, "VERIFY_RECORD_ABSENT")
    if t == M.MESSAGE:
        bad = rec.present and is_direct(rec)
        return Decision(rec.key, rec, "REPORT_EXPOSED_PII" if bad else None,
                        "REDACT_RECORD" if bad else None, "VERIFY_RECORD_REDACTED")
    if t == M.TOMBSTONE:
        bad = rec.present and (bool(rec.exposed) or is_direct(rec))
        return Decision(rec.key, rec, "REPORT_EXPOSED_PII" if bad else None,
                        "REDACT_RECORD" if bad else None, "VERIFY_RECORD_REDACTED")
    if t == M.ANALYTICS:
        bad = rec.present and (bool(rec.exposed) or is_direct(rec))
        return Decision(rec.key, rec, "REPORT_EXPOSED_PII" if bad else None,
                        "ANONYMIZE_RECORD" if bad else None, "VERIFY_RECORD_ANONYMIZED")
    if t == M.FLOW:
        bad = bool(rec.enabled)
        return Decision(rec.key, rec, "REPORT_ACTIVE_DATA_FLOW" if bad else None,
                        "DISABLE_DATA_FLOW" if bad else None, "VERIFY_DATA_FLOW_DISABLED")
    if t == M.BACKUP:
        bad = bool(rec.restore_allowed)
        return Decision(rec.key, rec, "REPORT_RESTORE_RISK" if bad else None,
                        "BLOCK_RESTORE" if bad else None, "VERIFY_RESTORE_BLOCKED")
    if t == M.AUDIT:
        return Decision(rec.key, rec, None, None, "VERIFY_RECORD_PRESENT")
    return None


def decide_status(decisions: list[Decision]) -> str:
    return "INCOMPLETE" if any(d.finding for d in decisions) else "COMPLETE"
