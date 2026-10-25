"""Ghost Data Still Exists - deletion audit agent.

    python code/main.py --sample            # 32 public samples -> .cache/sample_predictions.csv
    python code/main.py --full              # 518 evaluation requests -> output.csv (repo root)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ghost.config import CACHE_DIR, OUTPUT_CSV  # noqa: E402
from ghost.data import load_requests  # noqa: E402
from ghost.intent import requests_deletion  # noqa: E402
from ghost.llm import USAGE  # noqa: E402
from ghost.media import extract_media  # noqa: E402
from pipeline import Auditor  # noqa: E402


def make_auditor() -> Auditor:
    return Auditor(intent_fn=requests_deletion, media_fn=extract_media)


def run(sample: bool, out: Path) -> list[tuple[str, str, list[dict]]]:
    auditor = make_auditor()
    results, conflicts = [], []
    for row in sorted(load_requests(sample=sample), key=lambda r: r["case_id"]):
        status, steps = auditor.audit(row)
        results.append((row["case_id"], status, steps))
        claim = auditor.classify_claim(row)
        if claim and status != "NOT_APPLICABLE":
            conflicts.append(f"{row['case_id']}: request_text asks for deletion (decision {status}) but "
                             f"CLASSIFY_REQUEST claims non-deletion for {claim}")
        elif not claim and status == "NOT_APPLICABLE" and auditor.classified:
            conflicts.append(f"{row['case_id']}: request_text is not a deletion request but no CLASSIFY_REQUEST claim is linked")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "classify_conflicts.txt").write_text(chr(10).join(conflicts) + chr(10), encoding="utf-8")
    print(f"CLASSIFY_REQUEST contradictions: {len(conflicts)} (see .cache/classify_conflicts.txt)")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["case_id", "deletion_status", "steps_json"])
        for cid, status, steps in results:
            w.writerow([cid, status, json.dumps(steps, ensure_ascii=False, separators=(",", ":"))])
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sample", action="store_true")
    g.add_argument("--full", action="store_true")
    args = ap.parse_args()
    out = OUTPUT_CSV if args.full else CACHE_DIR / "sample_predictions.csv"
    results = run(sample=args.sample, out=out)
    print(f"wrote {len(results)} rows to {out}")
    if args.full:
        from evaluation.usage_report_writer import write
        print(f"usage report: {write(len(results))}")
    print(f"LLM calls={USAGE.calls} cache_hits={USAGE.cache_hits} in={USAGE.input_tokens} out={USAGE.output_tokens}")


if __name__ == "__main__":
    main()
