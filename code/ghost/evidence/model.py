"""Normalised evidence record used by every parser and by the state reconstruction."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
HASH_RE = re.compile(r"\b[0-9a-f]{64}\b")
USER_RE = re.compile(r"\buser_\d+\b")
PHONE_RE = re.compile(r"\+\d[\d ()\-]{6,}\d")

PREFIX_SYSTEM = {
    "account": "account_service",
    "search": "search_service",
    "support": "support_platform",
    "analytics": "analytics_platform",
    "export": "export_service",
    "data_flow": "integration_service",
    "backup": "backup_service",
    "audit_record": "security_service",
    "tombstone": "identity_service",
    "marketing": "marketing_platform",
    "object": "object_storage",
    "cache": "cache_service",
    "legal": "legal_service",
}

# logical record types (match deletion_rules.csv data_category where possible)
PROFILE, SEARCH, MESSAGE, ATTACHMENT, CONTACT = "USER_PROFILE", "SEARCH_INDEX_ENTRY", "SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT", "SUPPORT_CONTACT"
ANALYTICS, EXPORT, MARKETING, FLOW, BACKUP = "ANALYTICS_PROFILE", "USER_EXPORT", "MARKETING_PROFILE", "DATA_FLOW", "BACKUP_ARCHIVE"
AUDIT, TOMBSTONE, OBJECT, LEGAL = "SECURITY_AUDIT_LOG", "ACCOUNT_TOMBSTONE", "OBJECT", "LEGAL_HOLD_RECORD"


def prefix_of(resource_id: str) -> str:
    m = re.match(r"([a-z_]+?)_\d", resource_id)
    return m.group(1) if m else resource_id.split("_")[0]


def system_of(resource_id: str) -> str:
    return PREFIX_SYSTEM.get(prefix_of(resource_id), "unknown")


def default_rtype(resource_id: str) -> str:
    return {
        "account": PROFILE, "search": SEARCH, "support": MESSAGE, "analytics": ANALYTICS,
        "export": EXPORT, "data_flow": FLOW, "backup": BACKUP, "audit_record": AUDIT,
        "tombstone": TOMBSTONE, "marketing": MARKETING, "object": OBJECT, "legal": LEGAL,
    }.get(prefix_of(resource_id), "UNKNOWN")


@dataclass
class Rec:
    file_id: str
    ts: str                     # ISO time of the observation (<= audit_at filter uses this)
    resource_id: str
    rtype: str
    present: bool               # record exists in this observation
    system: str = ""
    emails: set = field(default_factory=set)
    phones: set = field(default_factory=set)
    hashes: set = field(default_factory=set)
    refs: set = field(default_factory=set)      # user_N style references
    enabled: bool | None = None                 # data flows
    restore_allowed: bool | None = None         # backups
    exposed: bool | None = None                 # record carries direct identifiers
    status: str = ""
    note: str = ""

    def __post_init__(self):
        if not self.system:
            self.system = system_of(self.resource_id)

    @property
    def key(self) -> tuple[str, str]:
        return (self.system, self.resource_id)


def absorb(rec: Rec, value) -> None:
    """Pull every identifier-looking token out of an arbitrary value into rec."""
    if value is None:
        return
    if isinstance(value, (list, tuple, set)):
        for v in value:
            absorb(rec, v)
        return
    if isinstance(value, dict):
        for v in value.values():
            absorb(rec, v)
        return
    s = str(value)
    for e in EMAIL_RE.findall(s):
        rec.emails.add(e.lower())
    for h in HASH_RE.findall(s.lower()):
        rec.hashes.add(h)
    for u in USER_RE.findall(s):
        rec.refs.add(u)
    for p in PHONE_RE.findall(s):
        rec.phones.add(norm_phone(p))


def norm_phone(p: str) -> str:
    return re.sub(r"[^\d+]", "", p)
