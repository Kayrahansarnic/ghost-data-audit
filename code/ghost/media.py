"""PDF / PNG evidence: pypdf text (PDF) or vision (PNG), structured into records by Claude Haiku."""
from __future__ import annotations

import base64
from pathlib import Path

from .evidence import model as M
from .evidence.loader import RESULT_TYPES
from .evidence.model import Rec, absorb
from .llm import call_haiku, parse_json

SYSTEM = (
    "You extract facts from business artifacts of a fictional commerce platform (invoices, support records, "
    "handover documents, internal admin screens). List every record that the artifact shows about a system "
    "resource. Do not judge whether anything should be deleted; only report what is visible. "
    'Return JSON only: {"records": [{"resource_id": str, "record_type": one of '
    + str(sorted(RESULT_TYPES))
    + ', "present": bool, "observed_at": ISO-8601 UTC string or null, "emails": [str], "phones": [str], '
    '"user_refs": ["user_N"], "email_hashes": [str], "has_name": bool, "enabled": bool|null, '
    '"restore_allowed": bool|null, "retain_until": str|null, "note": str}]}. '
    "Use SUPPORT_ATTACHMENT when the artifact is an uploaded file attached to a support case (a document, "
    "image or scan with a file name and upload history) and SUPPORT_MESSAGE for message text. "
    "A screen shows one record per resource: its resource id is usually printed in the page header or subtitle "
    "next to the customer name (for example 'support_1034 - Kofi Agyeman' or 'marketing_001 - e-mail - phone'); "
    "report that record even if the visible rows are only a conversation or activity list, and copy the customer "
    "e-mail, phone and name visibility (has_name) shown in the header or cards. A support conversation is "
    "SUPPORT_MESSAGE (a console view of a ticket thread), a document that is itself an uploaded file with attachment properties or upload history is SUPPORT_ATTACHMENT, a marketing audience profile is MARKETING_PROFILE. When a console lists files or objects "
    "without resource ids (an object browser), report each listed item with its file name as resource_id. "
    "resource_id must be copied exactly as printed (examples: account_123, support_001, audit_record_003, "
    "analytics_45, export_7, data_flow_9, backup_2, search_8, marketing_001, object_19, tombstone_17). "
    "Use null or [] when a field is not visible. Never invent identifiers. Copy emails and phone numbers verbatim."
)


def _records(fid: str, captured: str, data: dict) -> list[Rec]:
    out = []
    for d in data.get("records", []):
        rid = d.get("resource_id")
        if not rid:
            continue
        rtype = RESULT_TYPES.get(d.get("record_type") or "", M.default_rtype(rid))
        r = Rec(fid, d.get("observed_at") or captured, rid, rtype, bool(d.get("present", True)))
        for key in ("emails", "phones", "user_refs", "email_hashes"):
            for v in d.get(key) or []:
                absorb(r, v)
        if d.get("has_name"):
            r.note = "has_name"
        r.enabled = d.get("enabled")
        r.restore_allowed = d.get("restore_allowed")
        out.append(r)
    return out


def extract_media(fid: str, path: Path, captured: str) -> list[Rec]:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
        content = f"Artifact captured at {captured}. PDF text:\n<<<\n{text}\n>>>"
    else:
        b64 = base64.standard_b64encode(path.read_bytes()).decode()
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
            {"type": "text", "text": f"Artifact captured at {captured}. Extract the records shown in this screenshot."},
        ]
    data = parse_json(call_haiku("media", SYSTEM, content, max_tokens=3000))
    return _records(fid, captured, data)
