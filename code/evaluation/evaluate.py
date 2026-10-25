"""Score the pipeline on the 32 public samples: case, step, field and sequence accuracy."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost.data import load_expected, load_requests  # noqa: E402

FIELDS = ["phase", "system_id", "resource_id", "operation", "state", "evidence_id"]


def score(auditor, verbose: bool = True) -> dict:
    exp = load_expected()
    n = case_ok = seq_ok = 0
    step_tp = step_pred = step_gold = 0
    field_ok = field_tot = 0
    diffs = []
    for row in load_requests(sample=True):
        cid = row["case_id"]
        status, steps = auditor.audit(row)
        gold = json.loads(exp[cid]["steps_json"])
        n += 1
        case_ok += status == exp[cid]["deletion_status"]
        key = lambda s: tuple(s[f] for f in FIELDS)
        gk, pk = [key(s) for s in gold], [key(s) for s in steps]
        seq_ok += pk == gk and status == exp[cid]["deletion_status"]
        gset, pset = set(gk), set(pk)
        step_tp += len(gset & pset); step_pred += len(pset); step_gold += len(gset)
        for g, p in zip(gold, steps):
            for f in FIELDS:
                field_tot += 1; field_ok += g[f] == p[f]
        field_tot += abs(len(gold) - len(steps)) * len(FIELDS)
        if pk != gk or status != exp[cid]["deletion_status"]:
            diffs.append((cid, exp[cid]["deletion_status"], status, sorted(gset - pset), sorted(pset - gset)))
    res = {
        "cases": n, "case_accuracy": case_ok / n, "sequence_accuracy": seq_ok / n,
        "step_precision": step_tp / max(step_pred, 1), "step_recall": step_tp / max(step_gold, 1),
        "field_accuracy": field_ok / max(field_tot, 1),
    }
    if verbose:
        print(json.dumps(res, indent=1))
        for d in diffs:
            print(d[0], "gold", d[1], "pred", d[2]); print("   missing:", d[3]); print("   extra:  ", d[4])
    res["diffs"] = diffs
    return res


def main() -> None:
    from main import make_auditor  # code/main.py (code/ is first on sys.path)
    from ghost.llm import USAGE

    score(make_auditor())
    print("LLM calls", USAGE.calls, "cache hits", USAGE.cache_hits)


if __name__ == "__main__":
    main()
