"""For every gold step the pipeline misses on the samples, look for ANY trace in the participant files
that ties the resource to the case subject by exact identity. Read-only analysis.

Usage: python code/evaluation/audit_missing.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost.config import DATASET  # noqa: E402
from ghost.data import load_requests  # noqa: E402
from ghost.identity import IdentityIndex  # noqa: E402
from evaluate import score  # noqa: E402
from main import make_auditor  # noqa: E402


def corpus() -> list[tuple[str, str]]:
    """(source label, text) for every participant file; PDFs via pypdf; PNG handled separately by the LLM extraction."""
    out = []
    for p in sorted(DATASET.rglob("*")):
        if not p.is_file() or p.suffix.lower() in (".png",):
            continue
        rel = p.relative_to(DATASET).as_posix()
        if p.name in ("sample_output.csv", "output.csv"):  # answer key / template, never evidence
            continue
        if p.suffix.lower() == ".pdf":
            from pypdf import PdfReader
            out.append((rel, "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)))
        else:
            out.append((rel, p.read_text(encoding="utf-8", errors="replace")))
    return out


def main() -> None:
    aud = make_auditor()
    res = score(aud, verbose=False)
    ids = IdentityIndex()
    reqs = {r["case_id"]: r for r in load_requests(sample=True)}
    docs = corpus()
    print("| case | missing step | files mentioning the resource | exact-identity trace? | verdict |")
    print("|---|---|---|---|---|")
    for cid, gstatus, pstatus, missing, extra in res["diffs"]:
        subj = ids.resolve(reqs[cid]["email"])
        tokens = {t for t in subj.emails | subj.hashes | {subj.user_id}}
        for m in missing:
            phase, system, rid, op, state, ev = m
            hits, linked = [], []
            for rel, text in docs:
                if rid not in text:
                    continue
                hits.append(rel.split("/")[-1])
                lines = text.splitlines()
                for i, ln in enumerate(lines):
                    if re.search(rf"\b{re.escape(rid)}\b", ln):
                        ctx = "\n".join(lines[max(0, i - 3): i + 4]).lower()
                        if any(t.lower() in ctx for t in tokens):
                            linked.append(rel.split("/")[-1])
                            break
            verdict = "linkable by exact identity (source skipped)" if linked else "cannot be linked"
            print(f"| {cid} | {phase[:4]} {rid} {op} | {', '.join(sorted(set(hits))) or '-'} | "
                  f"{', '.join(sorted(set(linked))) or 'no'} | {verdict} |")


if __name__ == "__main__":
    main()
