"""Load the collusion.wiki export into plain Python structures (stdlib only)."""
import ast
import gzip
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

HOST_RE = re.compile(r"https?://([^/\s\]\)\"'<>|%]+)", re.I)


def _t(s):
    if not s or s == "None":
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def inserted_text(body, hunks_s):
    """Lines this revision added (insert/replace hunks), not the whole page."""
    lines = body.split("\n")
    try:
        hunks = ast.literal_eval(hunks_s) if hunks_s and hunks_s != "None" else None
    except Exception:
        hunks = None
    if not hunks:
        return body
    out = []
    for h in hunks:
        if h.get("op") in ("insert", "replace"):
            out.extend(lines[h["b0"]:h["b1"]])
    return "\n".join(out)


def hosts(text):
    return {h.lower().removeprefix("www.").rstrip(".:") for h in HOST_RE.findall(text)}


def load(path="data/raw/revisions.jsonl.gz"):
    revs = []
    for line in gzip.open(path, "rt"):
        r = json.loads(line)
        t = _t(r["time"])
        if t is None:
            continue
        ins = inserted_text(r["body"], r["hunks"])
        revs.append({
            "id": r["rev_id"],
            "page": r["page_id"],
            "label": r["label"] or "",  # '' = name redacted / missing
            "ip16": r["ip16"],
            "t": t,
            "body_hosts": hosts(r["body"]),
            "ins": ins,
            "ins_hosts": hosts(ins),
        })
    revs.sort(key=lambda r: (r["t"], r["id"]))
    return revs


def by_page(revs):
    d = defaultdict(list)
    for r in revs:
        d[r["page"]].append(r)
    return d


def by_label(revs):
    d = defaultdict(list)
    for r in revs:
        if r["label"]:
            d[r["label"]].append(r)
    return d
