"""Robustness: repeat graph + alarm using only 'strict' edges where the later agent
kept >= 50% of the earlier agent's lines (i.e. built on it rather than overwrote it)."""
import gzip, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swarmtrace.load import load, by_page, by_label
from swarmtrace.analyze import graph_stats, components
from swarmtrace.run import daily_group

R = load(); P = by_page(R); BL = by_label(R)
raw = {}
for l in gzip.open("data/raw/revisions.jsonl.gz", "rt"):
    r = json.loads(l); raw[r["rev_id"]] = r["body"]
E = []
for revs in P.values():
    for a, b in zip(revs, revs[1:]):
        if a["label"] and b["label"] and a["label"] != b["label"]:
            la = {x for x in raw[a["id"]].split("\n") if x.strip()}
            lb = {x for x in raw[b["id"]].split("\n") if x.strip()}
            if la and len(la & lb) / len(la) >= 0.5:
                E.append((a["label"], b["label"], b["t"], b["page"]))
g = graph_stats(E, BL); g.pop("out_deg_hist")
dg = daily_group(E)
out = {"strict_edges": len(E), "giant_component": g["giant_component"], "giant_frac": g["giant_frac"],
       "reciprocal_pairs": g["reciprocal_pairs"], "max_out": g["max_out"],
       "first_alarm_by_threshold": {th: min(d for d in dg if dg[d] >= th).isoformat() for th in (10, 20, 50, 100)}}
json.dump(out, open("results/robust_strict_edges.json", "w"), indent=1)
print(out)
