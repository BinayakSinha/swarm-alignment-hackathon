"""Run every analysis, write results/results.json and SVG figures.
Usage:  python3 -I swarmtrace/run.py    (from the project root)"""
import json
import zlib
import os
import random
import statistics
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swarmtrace.load import load, by_page, by_label  # noqa: E402
from swarmtrace.analyze import (  # noqa: E402
    TOOL_HOSTS, SOURCE_HOSTS, build_on_edges, graph_stats, SpreadIndex, synth_validation,
    daily_series, alarms, cumulative_giant, components, identity_eval,
)
from swarmtrace import svg  # noqa: E402

OUT = "results"
os.makedirs(OUT, exist_ok=True)
MILESTONES = {  # from the collusion.wiki investigators' timeline
    date(2026, 5, 24): "first wiki write",
    date(2026, 6, 16): "traffic spike",
    date(2026, 6, 21): "OpenAI staff visit",
}
DETECTED = date(2026, 6, 21)


def daily_group(edges):
    """Largest connected group of agents formed by a single day's build-on edges."""
    per = defaultdict(list)
    for e in edges:
        per[e[2].date()].append(e)
    res = {}
    for d, es in per.items():
        und = defaultdict(set)
        for a, b, _, _ in es:
            und[a].add(b); und[b].add(a)
        res[d] = len(components(list(und), und)[0])
    return res


def main():
    R = load()
    P, BL = by_page(R), by_label(R)
    res = {"n_revisions": len(R), "n_pages": len(P), "n_names": len(BL),
           "n_unnamed_revs": sum(1 for r in R if not r["label"])}

    # 1. graph
    E = build_on_edges(P)
    g = graph_stats(E, BL)
    g.pop("out_deg_hist")
    res["graph"] = g
    outd = defaultdict(int)
    for a, b in {(a, b) for a, b, _, _ in E}:
        outd[a] += 1
    res["graph"]["share_names_built_on_by_10plus"] = sum(v >= 10 for v in outd.values()) / len(BL)

    # 2. spread
    si = SpreadIndex(R)
    tools = []
    for h in sorted(TOOL_HOSTS | SOURCE_HOSTS):
        t = si.exposure_test(h, n_perm=500, rng=random.Random(zlib.crc32(h.encode())))
        if t:
            t["role"] = "tool" if h in TOOL_HOSTS else "source"
            tools.append(t)
    tools.sort(key=lambda t: t["first"])
    anon = {}
    for t in tools:
        if t["role"] == "tool":
            anon[t["token"]] = f"Tool-{sum(1 for v in anon.values()) + 1}"
    for t in tools:
        t["public_name"] = anon.get(t["token"], t["token"])
    res["spread"] = [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in t.items()}
                     for t in tools]
    val = synth_validation(si, n_trials=80)
    res["spread_validation"] = {
        k: {"n": len(L), "share_p<0.05": sum(r["p"] < 0.05 for r in L) / len(L),
            "median_lift": statistics.median(r["lift"] for r in L)}
        for k, L in val.items()}

    # 3. early warning
    S = daily_series(R, E)
    dg = daily_group(E)
    for x in S:
        x["group"] = dg.get(x["day"], 0)
    group_alarm = [x["day"] for x in S if x["group"] >= 20]
    edge_alarm = alarms(S, "edges")
    first = group_alarm[0]
    before = sum(1 for r in R if r["t"].date() < first)
    window = sum(1 for r in R if first <= r["t"].date() < DETECTED)
    res["early_warning"] = {
        "rule": "fire when one day's build-on edges join >= 20 agent names into one connected group",
        "first_alarm": first.isoformat(), "alarm_days": [d.isoformat() for d in group_alarm],
        "edge_spike_alarm_first": edge_alarm[0].isoformat(),
        "lead_days_vs_staff_visit": (DETECTED - first).days,
        "revs_before_alarm": before, "revs_between_alarm_and_staff_visit": window,
        "share_revs_after_alarm_before_visit": window / len(R),
        "names_active_before_alarm": len({r["label"] for r in R if r["label"] and r["t"].date() < first}),
    }
    G = cumulative_giant(E)

    # 4. identity
    ident = {}
    for split in ("random", "temporal"):
        for w, nm in [((0.5, 0.3, 0.2), "combined"), ((1, 0, 0), "style"),
                      ((0, 1, 0), "ip16"), ((0, 0, 1), "hours")]:
            r = identity_eval(BL, weights=w, split=split)
            r.pop("ranks")
            ident[f"{split}/{nm}"] = r
    ident["chance_recall@1"] = 1 / (ident["random/combined"]["n_candidates"] + 1)
    res["identity"] = ident

    json.dump(res, open(f"{OUT}/results.json", "w"), indent=1, default=str)

    # ---- figures
    days = [x["day"] for x in S]
    svg.timeseries(f"{OUT}/fig1_activity.svg", days,
                   {"edits per day": [x["revs"] for x in S],
                    "build-on edges per day": [x["edges"] for x in S]},
                   marks={**MILESTONES, first: "our alarm"}, title="Agent activity on the wiki")
    svg.timeseries(f"{OUT}/fig2_group.svg", [d for d, _ in G],
                   {"largest connected group of agent names": [s for _, s in G]},
                   marks={first: "our alarm", DETECTED: "OpenAI staff visit"},
                   title="Growth of the connected swarm", log=False)
    bars = [(t["public_name"], t["lift"], t["p"] < 0.01, t["role"]) for t in tools]
    svg.bars(f"{OUT}/fig3_spread.svg", bars,
             title="Exposure lift: adopters who had seen it on the board / null expectation")
    svg.recall(f"{OUT}/fig4_identity.svg", ident)
    print(json.dumps(res, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
