"""End-to-end: request row -> (status, steps)."""
from __future__ import annotations

from ghost import plan, policy, state
from ghost.data import load_activity
from ghost.evidence.loader import activity_links, alias_map, apply_aliases, load_all
from ghost.evidence.model import Rec, PROFILE
from ghost.identity import IdentityIndex


class Auditor:
    def __init__(self, intent_fn=None, media_fn=None) -> None:
        self.ids = IdentityIndex()
        activity = load_activity()
        recs = load_all(include_media=media_fn)
        apply_aliases(recs, alias_map(activity))
        self.idx = state.EvidenceIndex(recs + activity_links(activity))
        self.intent_fn = intent_fn
        # CLASSIFY_REQUEST rows are claims: used only to report contradictions with request_text.
        self.classified = {a["resource_id"]: a["event_time"] for a in activity
                           if a["event_type"] == "CLASSIFY_REQUEST"}

    def classify_claim(self, row: dict) -> str | None:
        """Activity id of a CLASSIFY_REQUEST 'non-deletion' claim about this subject's account, if any."""
        subj = self.ids.resolve(row["email"])
        if subj is None:
            return None
        for key in state.linked_keys(subj, self.idx, row["audit_at"]):
            if key[0] == "account_service" and self.classified.get(key[1], "9") <= row["audit_at"]:
                return key[1]
        return None

    def audit(self, row: dict) -> tuple[str, list[dict]]:
        if self.intent_fn is not None and not self.intent_fn(row["request_text"]):
            return "NOT_APPLICABLE", []
        subj = self.ids.resolve(row["email"])
        if subj is None:
            return "NOT_APPLICABLE", []
        st = state.reconstruct(subj, self.idx, row["audit_at"], row["requested_at"])
        decisions = [d for d in (policy.decide(r, c) for r, c in st.values()) if d]
        # A resource seen only in files captured after audit_at cannot be cited: no finding or
        # remediation from it; its required end state is verified only when the case is incomplete.
        uncited = [d for d in decisions if not d.cite]
        for d in uncited:
            d.finding = d.remediation = None
        cited = [d for d in decisions if d.cite]
        status = policy.decide_status(cited)
        decisions = cited if status == "COMPLETE" else cited + uncited
        if status == "INCOMPLETE":
            acct = state.unobserved_account(subj, self.idx, row["audit_at"], st)
            if acct:  # account known only through a link record: its end state must still be verified
                decisions.append(policy.Decision(acct, Rec("", row["audit_at"], acct[1], PROFILE, False),
                                                 None, None, "VERIFY_RECORD_ABSENT", ""))
        return status, plan.build_steps(decisions, status)
