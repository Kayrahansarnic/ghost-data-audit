"""Claude Haiku access with an on-disk response cache and usage accounting.

The cache key is the sha256 of the complete request payload sent to the model, so any change to the
prompt, the model, the parameters or an attached image produces a new entry.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field

from .config import API_KEY_ENV, CACHE_DIR, MODEL, PRICE_IN_PER_MTOK, PRICE_OUT_PER_MTOK

_lock = threading.Lock()
_EMPTY = {"calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0}


@dataclass
class Usage:
    calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    by_purpose: dict = field(default_factory=dict)
    used: dict = field(default_factory=dict)  # cache key -> (purpose, input_tokens, output_tokens), live or cached

    def add(self, purpose: str, inp: int, out: int) -> None:
        self.calls += 1
        self.input_tokens += inp
        self.output_tokens += out
        p = self.by_purpose.setdefault(purpose, dict(_EMPTY))
        p["calls"] += 1
        p["input_tokens"] += inp
        p["output_tokens"] += out

    def hit(self, purpose: str) -> None:
        self.cache_hits += 1
        self.by_purpose.setdefault(purpose, dict(_EMPTY))["cache_hits"] += 1

    @property
    def cost_usd(self) -> float:
        return self.input_tokens / 1e6 * PRICE_IN_PER_MTOK + self.output_tokens / 1e6 * PRICE_OUT_PER_MTOK


USAGE = Usage()
_client = None


def get_client():
    """Explicit client: the key comes only from CLAIM_AGENT_ANTHROPIC_KEY, never ANTHROPIC_API_KEY."""
    global _client
    if _client is None:
        import anthropic

        key = os.environ.get(API_KEY_ENV)
        if not key:
            raise RuntimeError(f"{API_KEY_ENV} is not set")
        _client = anthropic.Anthropic(api_key=key)
    return _client


def _key(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def call_haiku(purpose: str, system: str, content, max_tokens: int = 1500) -> str:
    """Return the model's text answer; identical requests are served from .cache/."""
    messages = [{"role": "user", "content": content}]
    payload = {"model": MODEL, "max_tokens": max_tokens, "system": system, "messages": messages}
    k = _key(payload)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{k}.json"
    if path.exists():
        entry = json.loads(path.read_text(encoding="utf-8"))
        with _lock:
            USAGE.hit(purpose)
            USAGE.used[k] = (purpose, entry.get("input_tokens", 0), entry.get("output_tokens", 0))
        return entry["text"]
    resp = get_client().messages.create(**payload)
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    with _lock:
        USAGE.add(purpose, resp.usage.input_tokens, resp.usage.output_tokens)
        USAGE.used[k] = (purpose, resp.usage.input_tokens, resp.usage.output_tokens)
    entry = {"text": text, "model": MODEL, "purpose": purpose,
             "input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    return text


def parse_json(text: str):
    t = text.strip()
    starts = [i for i in (t.find("{"), t.find("[")) if i >= 0]
    start = min(starts) if starts else 0
    end = max(t.rfind("}"), t.rfind("]"))
    return json.loads(t[start:end + 1])
