"""Normalise the many log syntaxes into flat dicts of key/value pairs."""
from __future__ import annotations

import json
import re

TS_RE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s+(.*)$")
KV_RE = re.compile(r'([A-Za-z_][\w.]*)=("(?:[^"\\]|\\.)*"|\S+)')
TRACE_RE = re.compile(r"\b(?:tr-rp-\w+|tr-\d+|rb-\d+-\d+)\b")
MSG_RE = re.compile(r'message=("(?:[^"\\]|\\.)*")')
BRACKET_RE = re.compile(r"\[(\w+)\]\s+\[(\w+)\]\s+\[([^\]]+)\]\s+(\w+):\s*(.*)$")
PIPE_RE = re.compile(r"\|?\s*(\w+)\s+\|\s+(\w+)\s+\|\s+([^|]+?)\s+\|\s+(\w+)\s+\|\s*(.*)$")
SYSLOG_RE = re.compile(r"<\d+>1\s+(\S+)\s+(\w+)\s+(\S+)\s+-\s+-\s*(.*)$")


def _unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return v


def _null(v: str):
    return None if v in ("null", "None", "") else v


def parse_line(line: str) -> dict | None:
    line = line.rstrip("\n")
    m = TS_RE.match(line)
    if not m:
        return None
    ts, rest = m.group(1), m.group(2)
    rec: dict = {"ts": ts}
    if rest.startswith("{"):
        try:
            data = json.loads(rest)
        except ValueError:
            return None
        for k, v in data.items():
            rec[k] = None if v in ("null", "") else v
        if "severity" in data:
            rec["level"] = data["severity"]
    else:
        body = rest
        mm = MSG_RE.search(rest)
        if mm:  # cloud runtime export carries the payload escaped inside message="..."
            body = rest[: mm.start()] + " " + _unquote(mm.group(1))
        br, pipe, sysl = BRACKET_RE.match(body), PIPE_RE.match(body), SYSLOG_RE.match(body)
        if br:
            rec.update(level=br.group(1), service=br.group(2), trace_id=br.group(3), event=br.group(4))
            body = br.group(5)
        elif pipe:
            rec.update(level=pipe.group(1), service=pipe.group(2), trace_id=pipe.group(3), event=pipe.group(4))
            body = pipe.group(5)
        elif sysl:
            rec.update(node=sysl.group(1), service=sysl.group(2), trace_id=sysl.group(3))
            body = sysl.group(4)
        for k, v in KV_RE.findall(body):
            rec[k] = _null(_unquote(v))
    if not rec.get("trace_id"):
        t = TRACE_RE.search(line.replace('\\"', '"'))
        if t:
            rec["trace_id"] = t.group(0)
    if not rec.get("trace_id") and rec.get("requestId"):
        rec["trace_id"] = rec["requestId"]
    if not rec.get("service") and rec.get("function"):
        rec["service"] = rec["function"]
    return rec


def parse_log(path) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            r = parse_line(line)
            if r:
                out.append(r)
    return out
