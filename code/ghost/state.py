"""Reconstruct, per subject and audit time, the latest citable state of every linked resource."""
from __future__ import annotations

from collections import defaultdict

from .data import load_manifest
from .evidence.model import Rec
from .identity import Subject

_CAPTURED = {r["file_id"]: r["captured_at"] for r in load_manifest()}


def file_captured(file_id: str) -> str:
    """Capture time of an evidence file; activity-derived link records have none."""
    return _CAPTURED.get(file_id, "")


class EvidenceIndex:
    """All Rec objects grouped by resource key, sorted by observation time."""

    def __init__(self, recs: list[Rec]) -> None:
        self.by_key: dict[tuple, list[Rec]] = defaultdict(list)
        for r in recs:
            self.by_key[r.key].append(r)
        for lst in self.by_key.values():
            lst.sort(key=lambda r: (r.ts, file_captured(r.file_id)))
        self.recs = recs


def linked_keys(subject: Subject, idx: EvidenceIndex, audit_at: str) -> set[tuple]:
    """Resources tied to the subject by an exact identifier (directly or via the same resource_id)."""
    keys = set()
    for r in idx.recs:
        if r.ts <= audit_at and subject.matches(r):
            keys.add(r.key)
    return keys


def latest_state(key: tuple, idx: EvidenceIndex, audit_at: str, since: str = "") -> tuple[Rec | None, str]:
    """State and citation of a resource at audit_at.

    A citable observation was made at or before audit_at inside a file captured at or before audit_at;
    the latest such observation decides the state and its file is the citation. If a resource was only
    seen in files captured after audit_at (even if an inner timestamp is earlier) the latest such
    observation is returned with citation "" and the pipeline must not report a finding from it.
    Evidence captured before `since` (the request time) predates the deletion request and say nothing
    about what the deletion did, so they are ignored for state."""
    citable = other = None
    for r in idx.by_key.get(key, []):
        if "link_only" in r.note or r.ts > audit_at or file_captured(r.file_id) < since:
            continue
        if file_captured(r.file_id) <= audit_at:
            citable = r
        else:
            other = r
    if citable is not None:
        return citable, citable.file_id
    return other, ""


def reconstruct(subject: Subject, idx: EvidenceIndex, audit_at: str, since: str = "") -> dict[tuple, tuple[Rec, str]]:
    out = {}
    for key in linked_keys(subject, idx, audit_at):
        rec, cite = latest_state(key, idx, audit_at, since)
        if rec is not None:
            out[key] = (rec, cite)
    # An email maps to one live account; earlier lookups of other account ids are stale readbacks.
    accounts = [k for k, (r, _) in out.items() if r.rtype == "USER_PROFILE"]
    if len(accounts) > 1:
        keep = max(accounts, key=lambda k: out[k][0].ts)
        for k in accounts:
            if k != keep:
                del out[k]
    return out


def unobserved_account(subject: Subject, idx: EvidenceIndex, audit_at: str, observed: dict) -> tuple | None:
    """Latest account resource tied to the subject only by a link record (e.g. the source account of a
    search document or a catalog link) that has no observation of its own."""
    if any(k[0] == "account_service" for k in observed):
        return None
    cands = [(r.ts, r.key) for r in idx.recs
             if r.key[0] == "account_service" and "link_only" in r.note and r.ts <= audit_at and subject.matches(r)]
    return max(cands)[1] if cands else None
