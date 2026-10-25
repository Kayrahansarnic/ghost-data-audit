# Usage report (final full-dataset run)

Run that produced `output.csv`: `python code/main.py --full`, 518 requests.

| Item | Value |
| --- | --- |
| Provider | Anthropic (Claude API) |
| Model | `claude-haiku-5-5` (only model used) |
| Distinct model calls behind this output | 390 |
| Live API calls made during this run | 0 |
| Responses served from the disk cache during this run | 533 of 533 (100.0%) |
| Input tokens | 153,494 |
| Output tokens | 40,491 |
| Total tokens | 193,985 |
| Average tokens per request | 374 (input 296, output 78) |
| Price assumed (prompts under 100K tokens) | 0.10 USD / Mtok input, 0.50 USD / Mtok output |
| Estimated total cost | 0.0356 USD |
| Estimated cost per request | 0.000069 USD |

## Per purpose (single model, so per-model totals equal the overall totals)

| Purpose | Distinct calls | Input tokens | Output tokens | Cost (USD) |
| --- | --- | --- | --- | --- |
| intent | 375 | 108,631 | 24,199 | 0.0230 |
| media | 15 | 44,863 | 16,292 | 0.0126 |
| **all** | **390** | **153,494** | **40,491** | **0.0356** |

## How the numbers are obtained

* `intent`: one call per request to decide from `request_text` whether deletion is requested.
* `media`: one call per PDF/PNG evidence file (15 files); PDF text is extracted with `pypdf` first.
* The cache key is the sha256 of the complete request payload. Tokens come from the usage figures the API returned
  when each response was first obtained and stored next to the cached response; every distinct request used
  by this run is counted once, whether it was answered live or from the cache in this particular run.
* Everything else (identity resolution, time filtering, policy, step ordering) is deterministic Python without model calls.
* Cost is an estimate from the stated prices; no API key or credential appears in this file.
