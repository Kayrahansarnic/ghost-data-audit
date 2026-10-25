"""Write code/evaluation/usage_report.md from the LLM usage recorded during a full run."""
from __future__ import annotations

from pathlib import Path

from ghost.config import MODEL, PRICE_IN_PER_MTOK, PRICE_OUT_PER_MTOK
from ghost.llm import USAGE

REPORT = Path(__file__).resolve().parent / "usage_report.md"


def write(n_requests: int) -> Path:
    per: dict[str, dict] = {}
    for purpose, inp, out in USAGE.used.values():
        p = per.setdefault(purpose, {"calls": 0, "in": 0, "out": 0})
        p["calls"] += 1; p["in"] += inp; p["out"] += out
    t_in = sum(p["in"] for p in per.values())
    t_out = sum(p["out"] for p in per.values())
    calls = sum(p["calls"] for p in per.values())
    cost = lambda i, o: i / 1e6 * PRICE_IN_PER_MTOK + o / 1e6 * PRICE_OUT_PER_MTOK
    uses = USAGE.calls + USAGE.cache_hits
    lines = [
        "# Usage report (final full-dataset run)",
        "",
        f"Run that produced `output.csv`: `python code/main.py --full`, {n_requests} requests.",
        "",
        "| Item | Value |",
        "| --- | --- |",
        "| Provider | Anthropic (Claude API) |",
        f"| Model | `{MODEL}` (only model used) |",
        f"| Distinct model calls behind this output | {calls} |",
        f"| Live API calls made during this run | {USAGE.calls} |",
        f"| Responses served from the disk cache during this run | {USAGE.cache_hits} of {uses} ({USAGE.cache_hits / max(uses, 1):.1%}) |",
        f"| Input tokens | {t_in:,} |",
        f"| Output tokens | {t_out:,} |",
        f"| Total tokens | {t_in + t_out:,} |",
        f"| Average tokens per request | {(t_in + t_out) / n_requests:,.0f} (input {t_in / n_requests:,.0f}, output {t_out / n_requests:,.0f}) |",
        f"| Price assumed (prompts under 100K tokens) | {PRICE_IN_PER_MTOK:.2f} USD / Mtok input, {PRICE_OUT_PER_MTOK:.2f} USD / Mtok output |",
        f"| Estimated total cost | {cost(t_in, t_out):.4f} USD |",
        f"| Estimated cost per request | {cost(t_in, t_out) / n_requests:.6f} USD |",
        "",
        "## Per purpose (single model, so per-model totals equal the overall totals)",
        "",
        "| Purpose | Distinct calls | Input tokens | Output tokens | Cost (USD) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, p in sorted(per.items()):
        lines.append(f"| {name} | {p['calls']} | {p['in']:,} | {p['out']:,} | {cost(p['in'], p['out']):.4f} |")
    lines += [
        f"| **all** | **{calls}** | **{t_in:,}** | **{t_out:,}** | **{cost(t_in, t_out):.4f}** |",
        "",
        "## How the numbers are obtained",
        "",
        "* `intent`: one call per request to decide from `request_text` whether deletion is requested.",
        "* `media`: one call per PDF/PNG evidence file (15 files); PDF text is extracted with `pypdf` first.",
        "* The cache key is the sha256 of the complete request payload. Tokens come from the usage figures the API returned",
        "  when each response was first obtained and stored next to the cached response; every distinct request used",
        "  by this run is counted once, whether it was answered live or from the cache in this particular run.",
        "* Everything else (identity resolution, time filtering, policy, step ordering) is deterministic Python without model calls.",
        "* Cost is an estimate from the stated prices; no API key or credential appears in this file.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return REPORT
