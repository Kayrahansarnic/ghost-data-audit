"""Decide from request_text (any language) whether the person actually asks for deletion."""
from __future__ import annotations

from .llm import call_haiku, parse_json

SYSTEM = (
    "You classify customer privacy requests for a commerce platform. The text may be in any language. "
    "Decide whether the person is asking for their account and/or personal data to be deleted or erased "
    "(including closing an account with removal of data, or asking to check and finish a failed or partial deletion). "
    "Requests for access, copies or exports of data, corrections, updates, marketing opt-out or unsubscribe, "
    "or anything else that is not deletion are NOT deletion requests, even if they mention an account. "
    "A message that explicitly says to keep or not delete the account or data is NOT a deletion request. "
    'Answer with JSON only: {"requests_deletion": true|false, "language": "<name>", "reason": "<short>"}.'
)


def classify_intent(request_text: str) -> dict:
    out = call_haiku("intent", SYSTEM, f"Request text:\n<<<\n{request_text}\n>>>", max_tokens=300)
    d = parse_json(out)
    d["requests_deletion"] = bool(d.get("requests_deletion"))
    return d


def requests_deletion(request_text: str) -> bool:
    return classify_intent(request_text)["requests_deletion"]
