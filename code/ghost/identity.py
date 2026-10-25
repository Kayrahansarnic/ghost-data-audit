"""Exact-match identity resolution from the identity snapshot plus the audit history."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .data import load_audit_log, load_identities
from .evidence.model import norm_phone


@dataclass
class Subject:
    user_id: str
    emails: set = field(default_factory=set)
    phones: set = field(default_factory=set)
    hashes: set = field(default_factory=set)

    def matches(self, rec) -> bool:
        return bool(
            (rec.emails & self.emails) or (rec.phones & self.phones)
            or (rec.hashes & self.hashes) or (rec.refs & {self.user_id})
        )


class IdentityIndex:
    def __init__(self) -> None:
        self.subjects: dict[str, Subject] = {}
        self.by_email: dict[str, str] = {}
        for r in load_identities():
            s = Subject(r["user_id"], {r["email"].lower()}, {norm_phone(r["phone"])}, {r["email_hash"].lower()})
            self.subjects[s.user_id] = s
        for a in load_audit_log():
            s = self.subjects.get(a["user_id"])
            if s is None:
                continue
            for v in (a["old_value"], a["new_value"]):
                f = a["field_name"]
                if f == "email":
                    s.emails.add(v.lower())
                elif f == "phone":
                    s.phones.add(norm_phone(v))
                elif f == "email_hash":
                    s.hashes.add(v.lower())
        for s in self.subjects.values():
            for e in s.emails:
                self.by_email[e] = s.user_id

    def resolve(self, email: str) -> Subject | None:
        uid = self.by_email.get(email.strip().lower())
        return self.subjects.get(uid) if uid else None
