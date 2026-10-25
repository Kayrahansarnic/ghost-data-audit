"""Structural validation of the root output.csv against the submission contract.

Usage: python code/evaluation/validate_output.py [path]
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost.config import OUTPUT_CSV  # noqa: E402
from ghost.data import load_activity, load_manifest, load_requests  # noqa: E402
from ghost.plan import FIND_ORDER, REME_ORDER, STATE, VERI_ORDER  # noqa: E402

PHASE_OPS = {"FINDING": FIND_ORDER, "REMEDIATION": REME_ORDER, "VERIFICATION": VERI_ORDER}
FIELDS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    with open(path, encoding="utf-8", newline="") as fh:
        rdr = csv.reader(fh)
        header = next(rdr)
        rows = list(rdr)
    if header != ["case_id", "deletion_status", "steps_json"]:
        errors.append(f"bad header {header}")
    reqs = {r["case_id"]: r for r in load_requests()}
    ids = [r[0] for r in rows]
    if len(rows) != 518 or len(reqs) != 518:
        errors.append(f"row count {len(rows)}")
    if ids != sorted(ids):
        errors.append("rows not sorted by case_id")
    if set(ids) != set(reqs) or len(set(ids)) != len(ids):
        errors.append("case_id set differs from deletion_requests.csv or has duplicates")
    captured = {m["file_id"]: m["captured_at"] for m in load_manifest()}
    activity = {a["activity_id"]: a["event_time"] for a in load_activity()}
    counts = {"COMPLETE": 0, "INCOMPLETE": 0, "NOT_APPLICABLE": 0}
    for cid, status, steps_json in rows:
        if status not in counts:
            errors.append(f"{cid}: bad status {status}")
            continue
        counts[status] += 1
        try:
            steps = json.loads(steps_json)
        except ValueError:
            errors.append(f"{cid}: steps_json is not valid JSON")
            continue
        if not isinstance(steps, list):
            errors.append(f"{cid}: steps_json is not a list")
            continue
        if (status == "NOT_APPLICABLE") != (steps == []):
            errors.append(f"{cid}: NOT_APPLICABLE must be exactly []")
        audit_at = reqs[cid]["audit_at"] if cid in reqs else ""
        last_key = None
        phases_seen = []
        for i, s in enumerate(steps, 1):
            if set(s) != FIELDS:
                errors.append(f"{cid}: step {i} has fields {sorted(s)}")
                continue
            if s["step_no"] != i:
                errors.append(f"{cid}: step_no {s['step_no']} at position {i}")
            ops = PHASE_OPS.get(s["phase"])
            if ops is None or s["operation"] not in ops or STATE.get(s["operation"]) != s["state"]:
                errors.append(f"{cid}: step {i} bad phase/operation/state {s['phase']}/{s['operation']}/{s['state']}")
                continue
            key = (list(PHASE_OPS).index(s["phase"]), ops.index(s["operation"]), s["system_id"], s["resource_id"])
            if last_key is not None and key < last_key:
                errors.append(f"{cid}: step {i} out of order")
            last_key = key
            ev = s["evidence_id"]
            future = s["phase"] == "REMEDIATION" or (s["phase"] == "VERIFICATION" and status == "INCOMPLETE")
            if future and ev != "":
                errors.append(f"{cid}: step {i} future step cites {ev}")
            if s["phase"] == "FINDING" and not ev:
                errors.append(f"{cid}: finding step {i} without evidence")
            if ev:
                when = captured.get(ev) or activity.get(ev)
                if when is None:
                    errors.append(f"{cid}: step {i} cites unknown evidence {ev}")
                elif when > audit_at:
                    errors.append(f"{cid}: step {i} cites {ev} captured {when} after audit_at {audit_at}")
        if status == "COMPLETE":
            if not steps or any(s["phase"] != "VERIFICATION" or not s["evidence_id"] for s in steps):
                errors.append(f"{cid}: COMPLETE needs only evidence-backed verification steps")
        if status == "INCOMPLETE" and not any(s["phase"] == "FINDING" for s in steps):
            errors.append(f"{cid}: INCOMPLETE without findings")
    print(f"rows={len(rows)} status counts={counts}")
    return errors


if __name__ == "__main__":
    errs = validate(Path(sys.argv[1]) if len(sys.argv) > 1 else OUTPUT_CSV)
    print("OK" if not errs else f"{len(errs)} problems")
    for e in errs[:40]:
        print(" -", e)
    sys.exit(1 if errs else 0)
