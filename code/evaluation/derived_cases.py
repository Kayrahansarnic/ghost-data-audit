"""End-to-end extra evaluation cases derived from sample requests by controlled mutations.

(a) request_text replaced by a data-copy request            -> NOT_APPLICABLE and []
(b) request e-mail replaced by an older e-mail of the person -> identical output to the original
(c) request e-mail upper-cased                                -> identical output to the original
(d) audit_at moved before the capture time of cited evidence -> that evidence is no longer cited

Usage: python code/evaluation/derived_cases.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost.data import load_audit_log, load_manifest, load_requests  # noqa: E402
from ghost.identity import IdentityIndex  # noqa: E402
from ghost.state import file_captured  # noqa: E402
from main import make_auditor  # noqa: E402

DATA_COPY = ("Please send me a complete copy of all personal data you hold about me. "
             "I am not asking you to delete or close anything.")


def run() -> list[tuple[str, bool, str]]:
    aud = make_auditor()
    ids = IdentityIndex()
    rows = {r["case_id"]: r for r in load_requests(sample=True)}
    old_emails: dict[str, str] = {}
    for a in load_audit_log():
        if a["field_name"] == "email":
            old_emails.setdefault(a["user_id"], a["old_value"])
    out = []

    # (a) non-deletion request text
    for cid in ("case_11", "case_05"):
        row = dict(rows[cid], request_text=DATA_COPY)
        status, steps = aud.audit(row)
        out.append((f"a:{cid}", status == "NOT_APPLICABLE" and steps == [], f"status={status} steps={len(steps)}"))

    # (b) old e-mail of the same person
    n = 0
    for cid, row in rows.items():
        subj = ids.resolve(row["email"])
        old = old_emails.get(subj.user_id)
        if old and old.lower() != row["email"].lower():
            base = aud.audit(row)
            alt = aud.audit(dict(row, email=old))
            out.append((f"b:{cid}", alt == base, f"old={old} status={alt[0]} same_steps={alt[1] == base[1]}"))
            n += 1
    if n == 0:
        out.append(("b:none-available", False, "no sample subject has an older e-mail"))

    # (c) upper-case e-mail
    for cid in ("case_11", "case_12", "case_24"):
        row = rows[cid]
        out.append((f"c:{cid}", aud.audit(dict(row, email=row["email"].upper())) == aud.audit(row), "upper-cased e-mail"))

    # (d) audit_at before the capture time of cited evidence
    manifest = {m["file_id"]: m["captured_at"] for m in load_manifest()}
    for cid, cut in (("case_05", "2026-09-02T22:00:00Z"), ("case_24", "2026-09-15T09:00:00Z"),
                     ("case_11", "2026-10-01T11:00:00Z")):
        row = dict(rows[cid], audit_at=cut)
        status, steps = aud.audit(row)
        cited = {s["evidence_id"] for s in steps if s["evidence_id"]}
        late = sorted(e for e in cited if manifest.get(e, "") > cut)
        out.append((f"d:{cid}", not late, f"audit_at={cut} status={status} cited={sorted(cited)} late={late}"))
    return out


if __name__ == "__main__":
    for name, ok, detail in run():
        print(("PASS" if ok else "FAIL"), name, detail)
