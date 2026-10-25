"""Parse every evidence file into normalised Rec objects (deterministic, no LLM)."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from ..config import EVIDENCE_DIR
from ..data import load_manifest
from . import model as M
from .logslines import parse_log
from .model import Rec, absorb

ID_KEYS = {"email", "owner_email", "customer_email", "requester_email", "lookup_key", "match_key",
           "subject_key", "subject_ref", "scan_key", "owner_key", "correlation_key", "subject_reference",
           "customer_reference", "subject_selector", "user_id", "matched_value", "email_hash", "phone",
           "owner_phone", "requester_phone", "subject_ref", "source_user_id"}
NAME_KEYS = {"full_name", "name", "display_name", "requester_name"}
NOT_ID_KEYS = {"resource_id", "archive_key", "archive_path", "object_key", "file_name", "connector_name"}


def _bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    return str(v).strip().lower() in ("1", "true", "yes")


def rec_from_dict(file_id: str, ts: str, rid: str, rtype: str, d: dict, present: bool = True,
                  system: str = "") -> Rec:
    r = Rec(file_id=file_id, ts=ts, resource_id=rid, rtype=rtype, present=present, system=system)
    has_name = False
    for k, v in (d or {}).items():
        if k in NOT_ID_KEYS or v is None:
            continue
        if k in NAME_KEYS:
            has_name = has_name or bool(v)
            continue
        if isinstance(v, dict):
            sub = rec_from_dict(file_id, ts, rid, rtype, v, present)
            r.emails |= sub.emails; r.phones |= sub.phones; r.hashes |= sub.hashes; r.refs |= sub.refs
            has_name = has_name or "has_name" in sub.note
            continue
        if k in ("enabled",):
            r.enabled = _bool(v)
        elif k in ("restore_allowed",):
            r.restore_allowed = _bool(v)
        elif k in ("account_status", "status"):
            r.status = str(v)
        elif k in ("message_text", "message_excerpt"):
            if str(v).strip() != "[REDACTED]":
                absorb(r, v)
        elif k in ID_KEYS or k.endswith("_email") or k.endswith("_phone"):
            absorb(r, v)
    if has_name:
        r.note = "has_name"
    return r


def is_direct(r: Rec) -> bool:
    return bool(r.emails or r.phones or r.hashes or "has_name" in r.note)


# ---------------------------------------------------------------- logs

START_KEYS = ("lookup_key", "match_key", "subject_key", "subject_ref", "scan_key", "owner_key")


def parse_trace_log(fid: str, path: Path) -> list[Rec]:
    lines = parse_log(path)
    out: list[Rec] = []
    groups: dict[str, list[dict]] = defaultdict(list)
    for ln in lines:
        if ln.get("event") == "record_lookup":
            out.extend(_record_lookup(fid, ln["ts"], ln))
        elif ln.get("trace_id"):
            groups[ln["trace_id"]].append(ln)
    for tid, evs in groups.items():
        keys = {}
        for e in evs:
            for k in START_KEYS:
                if e.get(k):
                    keys[k] = e[k]
        for e in evs:
            r = _trace_event(fid, e, keys)
            if r:
                out.append(r)
    return out


def _link(r: Rec, e: dict, keys: dict) -> Rec:
    for v in keys.values():
        absorb(r, v)
    for k in ("correlation_key", "email", "customer_email", "customer_reference", "requester_email",
              "owner_email", "phone", "requester_phone", "matched_value", "subject_reference", "email_hash"):
        if e.get(k):
            absorb(r, e[k])
    return r


def _trace_event(fid: str, e: dict, keys: dict) -> Rec | None:
    ev, rid, ts = e.get("event"), e.get("resource_id"), e["ts"]
    if not rid:
        return None
    if ev == "profile_lookup_completed":
        present = str(e.get("rows")) not in ("0",) and str(e.get("http_status")) != "404"
        r = Rec(fid, ts, rid, M.PROFILE, present)
        r = _link(r, e, keys)
        if e.get("phone") or e.get("email"):
            r.note = "profile_fields"
        return r
    if ev == "index_query_completed":
        r = Rec(fid, ts, rid, M.SEARCH, e.get("result") == "hit")
        return _link(r, e, keys)
    if ev == "audit_record_read_completed":
        r = Rec(fid, ts, rid, M.AUDIT, str(e.get("rows")) != "0")
        return _link(r, e, keys)
    if ev == "message_pii_scan":
        r = Rec(fid, ts, rid, M.MESSAGE, True)
        _link(r, e, keys)
        r.note = "has_name" if not (r.emails or r.phones) else ""
        return r
    if ev == "message_read":
        r = Rec(fid, ts, rid, M.MESSAGE, True)
        _link(r, e, {})
        if e.get("message_text") and e["message_text"] != "[REDACTED]":
            absorb(r, e["message_text"])
        return r
    if ev == "support_ticket_read_completed":
        r = Rec(fid, ts, rid, M.MESSAGE, True)
        _link(r, e, keys)
        if e.get("requester_name"):
            r.note = "has_name"
        return r
    if ev == "attachment_pii_scan":
        r = Rec(fid, ts, rid, M.ATTACHMENT, True)
        return _link(r, e, keys)
    if ev == "analytics_identity_scan":
        r = Rec(fid, ts, rid, M.ANALYTICS, True)
        _link(r, e, keys)
        r.exposed = True
        return r
    if ev == "analytics_profile_read":
        r = Rec(fid, ts, rid, M.ANALYTICS, True)
        _link(r, e, keys)
        r.exposed = str(e.get("direct_identifiers", "0")) not in ("0", "")
        return r
    if ev == "analytics_profile_read_completed":
        r = Rec(fid, ts, rid, M.ANALYTICS, True)
        return _link(r, e, keys)
    if ev == "contact_lookup_completed":
        r = Rec(fid, ts, rid, M.MARKETING, str(e.get("rows")) != "0")
        return _link(r, e, keys)
    if ev in ("contact_query_completed",):
        r = Rec(fid, ts, rid, M.CONTACT, str(e.get("rows")) != "0")
        return _link(r, e, keys)
    if ev == "deletion_marker_check":
        r = Rec(fid, ts, rid, M.CONTACT, str(e.get("marker_found")).lower() != "true")
        r.note = "marker_check"
        return _link(r, e, keys)
    if ev == "restore_policy_read_completed":
        r = Rec(fid, ts, rid, M.BACKUP, True)
        r.restore_allowed = _bool(e.get("restore_allowed"))
        return _link(r, e, keys)
    if ev == "restore_candidate_evaluated":
        r = Rec(fid, ts, rid, M.BACKUP, True)
        r.restore_allowed = _bool(e.get("eligible")) and not _bool(e.get("deletion_block"))
        return _link(r, e, keys)
    if ev == "restore_authorization_completed":
        r = Rec(fid, ts, rid, M.BACKUP, True)
        r.restore_allowed = str(e.get("decision")).lower() != "deny"
        return _link(r, e, keys)
    if ev in ("connector_config_read_completed", "connector_heartbeat", "connector_config_loaded"):
        r = Rec(fid, ts, rid, M.FLOW, True)
        r.enabled = _bool(e.get("enabled"))
        return _link(r, e, keys)
    if ev in ("export_metadata_read_completed", "export_download_check_completed"):
        r = Rec(fid, ts, rid, M.EXPORT, str(e.get("available")).lower() != "false")
        return _link(r, e, keys)
    return None


RESULT_TYPES = {
    "USER_PROFILE": M.PROFILE, "SEARCH_INDEX_ENTRY": M.SEARCH, "SECURITY_AUDIT_LOG": M.AUDIT,
    "ANALYTICS_PROFILE": M.ANALYTICS, "DATA_FLOW": M.FLOW, "SUPPORT_MESSAGE": M.MESSAGE,
    "SUPPORT_ATTACHMENT": M.ATTACHMENT, "BACKUP_ARCHIVE": M.BACKUP, "USER_EXPORT": M.EXPORT,
    "MARKETING_PROFILE": M.MARKETING, "ACCOUNT_TOMBSTONE": M.TOMBSTONE, "LEGAL_HOLD_RECORD": M.LEGAL,
    "SEARCH_INDEX": M.SEARCH, "CACHE_ENTRY": "CACHE_ENTRY", "EMAIL_DELIVERY_LOG": "EMAIL_DELIVERY_LOG",
    "SECONDARY_IDENTIFIER": "SECONDARY_IDENTIFIER", "PRODUCT_TELEMETRY": "PRODUCT_TELEMETRY",
}


def _record_lookup(fid: str, ts: str, e: dict) -> list[Rec]:
    rid = e["resource_id"]
    rt = RESULT_TYPES.get(e.get("record_type", ""), M.default_rtype(rid))
    res = str(e.get("result", "")).upper()
    system = e.get("system") or ""
    r = Rec(fid, ts, rid, rt, res not in ("NOT_FOUND", "ABSENT", "DELETED"), system=system)
    ref = e.get("subject_reference")
    if ref and "no direct identifier" not in str(ref):
        absorb(r, ref)
    if rt == M.FLOW:
        r.enabled = res == "ACTIVE"
    elif rt == M.BACKUP:
        r.restore_allowed = res == "ACTIVE"
    elif rt == M.ANALYTICS:
        r.exposed = res == "IDENTIFIABLE"
    elif rt == M.MESSAGE:
        if res == "REDACTED":
            r.emails.clear(); r.phones.clear(); r.hashes.clear()
    elif rt == M.TOMBSTONE:
        r.exposed = res in ("IDENTIFIABLE", "PRESENT", "FOUND")
    r.status = res
    return [r]


# ---------------------------------------------------------------- txt / manifests

def parse_handover(fid: str, path: Path) -> list[Rec]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.lstrip("- ").split("|")]
        if len(parts) == 6 and re.match(r"\d{4}-\d\d-\d\dT", parts[0]):
            ts, system, rid, rtype, res, ref = parts
            out.extend(_record_lookup(fid, ts, dict(resource_id=rid, record_type=rtype, result=res,
                                                    system=system, subject_reference=ref)))
    return out


def parse_manifest_json(fid: str, data: dict) -> list[Rec]:
    out = []
    for e in data.get("records", []):
        out.extend(_record_lookup(fid, e["recorded_at"], e))
    return out


# ---------------------------------------------------------------- JSON snapshots

COLLECTION_TYPES = {
    "customer_profiles": M.PROFILE, "customer_search_documents": M.SEARCH,
    "customer_analytics_reports": M.ANALYTICS, "support_conversations": M.MESSAGE,
    "support_attachments": M.ATTACHMENT, "security_audit_events": M.AUDIT, "backup_catalog": M.BACKUP,
    "connector_configurations": M.FLOW, "customer_export_jobs": M.EXPORT,
    "deleted_customer_references": M.TOMBSTONE, "marketing_profiles": M.MARKETING,
    "legal_holds": M.LEGAL,
}


def _json_record(fid: str, ts: str, rtype_hint: str | None, d: dict, rtype_override: str | None = None) -> Rec:
    rid = d["resource_id"]
    rtype = rtype_override or rtype_hint or M.default_rtype(rid)
    ts = d.get("observed_at") or d.get("recorded_at") or ts
    present = True
    if rtype == M.PROFILE and "status_code" in d:
        present = d["status_code"] == 200
        d = dict(d.get("profile") or {}, resource_id=rid)
    if rtype == M.EXPORT and d.get("download_available") is False:
        present = False
    r = rec_from_dict(fid, ts, rid, rtype, d, present)
    if rtype == M.MESSAGE and d.get("channel") == "attachment":
        r.rtype = M.ATTACHMENT
    return r


def parse_bundle(fid: str, data: dict, captured: str) -> list[Rec]:
    out = []
    for snap in data.get("snapshots", []):
        ts = snap.get("captured_at", captured)
        hint = COLLECTION_TYPES.get(snap.get("collection"))
        for d in snap.get("records", []):
            if "resource_id" in d:
                out.append(_json_record(fid, ts, hint, d))
    return out


EXPORT_SECTIONS = {
    "profile_lookups": M.PROFILE, "profiles": M.ANALYTICS, "restore_entries": M.BACKUP,
    "exports": M.EXPORT, "connectors": M.FLOW, "documents": M.SEARCH, "search_results": M.SEARCH,
    "tickets": M.MESSAGE, "audit_records": M.AUDIT,
}


def parse_service_export(fid: str, data: dict, captured: str) -> list[Rec]:
    out = []
    for svc, sections in data.get("service_exports", {}).items():
        for sect, items in sections.items():
            for d in items:
                if "resource_id" not in d:
                    continue
                hint = EXPORT_SECTIONS.get(sect)
                out.append(_json_record(fid, data.get("exported_at", captured), hint, d))
    return out


def parse_single_collection(fid: str, data: dict) -> list[Rec]:
    hint = COLLECTION_TYPES.get(data.get("collection"))
    return [_json_record(fid, data.get("captured_at", ""), hint, d) for d in data.get("records", [])
            if "resource_id" in d]


# ---------------------------------------------------------------- SQL

def _sql_rows(path: Path):
    text = path.read_text(encoding="utf-8")
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(text)
    names = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    for t in names:
        for row in con.execute(f'select * from "{t}"'):
            yield t, dict(row)
    con.close()


TABLE_TYPES = {
    "customer_profiles": M.PROFILE, "customer_search_documents": M.SEARCH,
    "customer_analytics_profiles": M.ANALYTICS, "support_records": M.MESSAGE,
    "customer_exports": M.EXPORT, "connector_subscriptions": M.FLOW, "backup_restore_entries": M.BACKUP,
    "security_audit_records": M.AUDIT, "search_documents_primary": M.SEARCH,
}


def parse_sql(fid: str, path: Path, captured: str) -> list[Rec]:
    out = []
    for table, row in _sql_rows(path):
        if table == "snapshot_scope":
            continue
        if "record_json" in row:
            d = json.loads(row["record_json"])
            hint = COLLECTION_TYPES.get(row.get("collection_name"))
            r = _json_record(fid, captured, hint, d)
            r.note = (r.note + " " + table).strip()
            out.append(r)
            continue
        base = re.sub(r"_(primary|failover_replica|read_replica|reporting_replica)$", "", table)
        rtype = TABLE_TYPES.get(table) or TABLE_TYPES.get(base)
        if rtype is None or "resource_id" not in row:
            continue
        status = row.get("account_status")
        present = True
        r = rec_from_dict(fid, captured, row["resource_id"], rtype, row, present)
        r.note = (r.note + " " + table).strip()
        out.append(r)
        src = row.get("source_resource_id")
        if src:  # the document names the account it was built from: an identity link for that account
            link = Rec(fid, captured, src, M.default_rtype(src), True, emails=set(r.emails), phones=set(r.phones),
                       hashes=set(r.hashes), refs=set(r.refs), note="link_only source_resource_id")
            out.append(link)
    return out


# ---------------------------------------------------------------- driver

def load_all(include_media=None) -> list[Rec]:
    """Return every Rec from every evidence file. `include_media` is an optional callable
    (fid, path, captured) -> list[Rec] used for PDFs / PNGs (LLM backed)."""
    recs: list[Rec] = []
    for row in load_manifest():
        fid, rel, captured = row["file_id"], row["file_path"], row["captured_at"]
        path = EVIDENCE_DIR.parent / rel
        suffix = path.suffix.lower()
        try:
            if suffix == ".log":
                found = parse_trace_log(fid, path)
            elif suffix == ".txt":
                found = parse_handover(fid, path)
            elif suffix == ".sql":
                found = parse_sql(fid, path, captured)
            elif suffix == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                if "service_exports" in data:
                    found = parse_service_export(fid, data, captured)
                elif "snapshots" in data:
                    found = parse_bundle(fid, data, captured)
                elif data.get("records") and "record_type" in data["records"][0]:
                    found = parse_manifest_json(fid, data)
                else:
                    found = parse_single_collection(fid, data)
            elif suffix in (".pdf", ".png") and include_media is not None:
                found = include_media(fid, path, captured)
            else:
                found = []
        except Exception as exc:  # keep going; report loudly
            raise RuntimeError(f"failed parsing {fid} {rel}: {exc}") from exc
        for r in found:
            r.note = (r.note + f" src={fid}").strip()
            if not r.ts:
                r.ts = captured
        recs.extend(found)
    return recs


def activity_links(rows: list[dict]) -> list[Rec]:
    """LINK_RESOURCE_IDENTITY activity rows state which identifiers a resource belongs to.
    They tie identity to a resource but say nothing about its state, so they are link-only."""
    out = []
    for a in rows:
        if a["event_type"] != "LINK_RESOURCE_IDENTITY":
            continue
        r = Rec(a["activity_id"], a["event_time"], a["resource_id"], M.default_rtype(a["resource_id"]), True,
                system=a["target_system"], note="link_only activity_link")
        absorb(r, a["details"])
        out.append(r)
    return out


ALIAS_RE = re.compile(r"\(([^()\s]+)\)")


def alias_map(rows: list[dict]) -> dict[str, tuple[str, str]]:
    """Catalog links name a display alias in parentheses (e.g. a file name shown by a console instead of the
    resource id): alias -> (system_id, resource_id)."""
    out = {}
    for a in rows:
        if a["event_type"] != "LINK_RESOURCE_IDENTITY":
            continue
        m = ALIAS_RE.search(a["details"])
        if m and m.group(1) != a["resource_id"]:
            out[m.group(1)] = (a["target_system"], a["resource_id"])
    return out


def apply_aliases(recs: list[Rec], aliases: dict[str, tuple[str, str]]) -> int:
    """Re-key observations that display an alias so they join the linked resource id."""
    n = 0
    for r in recs:
        if "link_only" not in r.note and r.resource_id in aliases:
            r.system, r.resource_id = aliases[r.resource_id]
            n += 1
    return n
