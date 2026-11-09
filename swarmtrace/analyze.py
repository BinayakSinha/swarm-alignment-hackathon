"""Forensic analyses of the collusion.wiki agent swarm.

1. interaction graph  - who built on whose writing
2. spread             - did techniques spread by exposure, or appear independently?
3. early warning      - when would simple alarms on the graph have fired?
4. identity           - can we re-link one agent's edits across names?
"""
import math
import random
from collections import Counter, defaultdict
from datetime import timedelta

# Host roles. Tool hosts are fetch/proxy/relay services used to work around the
# read-only network limit; in the report they are anonymised as Tool-1..N.
TOOL_HOSTS = {
    "jqp.vercel.app", "md.succ.ai", "markdown.new", "allorigins.hexlet.app", "r.jina.ai",
    "api.counterapi.dev", "pure.md", "cors.bwa.workers.dev", "webcrawlerapi.com",
    "tinyurl.com", "proxymule.com", "md.dhr.wtf", "corsmirror.com", "api.allorigins.win",
}
SOURCE_HOSTS = {
    "api.datausa.io", "sec.gov", "investor.gov", "api-la.datausa.io", "api.usaspending.gov",
    "datausa.io", "api.census.gov",
}


# ---------------------------------------------------------------- 1. graph
def build_on_edges(pages):
    """Edge (B -> A) each time agent A saves a page whose previous save was B's.
    Editing a wiki page means loading its current text, so A demonstrably read B."""
    edges = []
    for revs in pages.values():
        prev = None
        for r in revs:
            if prev and r["label"] and prev["label"] and r["label"] != prev["label"]:
                edges.append((prev["label"], r["label"], r["t"], r["page"]))
            prev = r
    return edges


def components(nodes, und):
    seen, comps = set(), []
    for n in nodes:
        if n in seen:
            continue
        stack, comp = [n], []
        seen.add(n)
        while stack:
            x = stack.pop()
            comp.append(x)
            for y in und[x]:
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        comps.append(comp)
    return sorted(comps, key=len, reverse=True)


def graph_stats(edges, labels):
    w = Counter((a, b) for a, b, _, _ in edges)
    und = defaultdict(set)
    for a, b in w:
        und[a].add(b)
        und[b].add(a)
    for l in labels:
        und[l]
    comps = components(list(und), und)
    out_deg = Counter()
    in_deg = Counter()
    for (a, b) in w:
        out_deg[a] += 1
        in_deg[b] += 1
    recip = sum(1 for (a, b) in w if (b, a) in w) // 2
    return {
        "n_nodes": len(und), "n_edges_distinct": len(w), "n_edge_events": len(edges),
        "n_isolated": sum(1 for c in comps if len(c) == 1),
        "giant_component": len(comps[0]), "giant_frac": len(comps[0]) / len(und),
        "reciprocal_pairs": recip,
        "top_sources": out_deg.most_common(10),  # whose writing most others built on
        "out_deg_hist": Counter(out_deg.values()),
        "max_out": max(out_deg.values()), "median_out": sorted(out_deg.values())[len(out_deg) // 2],
    }


# ---------------------------------------------------------------- 2. spread
class SpreadIndex:
    """Holds per-label edit histories and per-page token arrival times."""

    def __init__(self, revs):
        self.revs = revs
        self.by_label = defaultdict(list)
        for r in revs:
            if r["label"]:
                self.by_label[r["label"]].append(r)

    def page_first(self, token, extra=None):
        """page -> (time, label) when the token first appeared on that page."""
        pf = {}
        for r in self.revs:
            if token in r["body_hosts"] or (extra and r["id"] in extra):
                if r["page"] not in pf:
                    pf[r["page"]] = (r["t"], r["label"])
        return pf

    def adopters(self, token, extra=None):
        ad = {}
        for r in self.revs:
            if r["label"] and (token in r["ins_hosts"] or (extra and r["id"] in extra)):
                ad.setdefault(r["label"], r["t"])
        return ad

    def exposed(self, label, t, pf):
        """Did `label` edit (load) a page that already carried the token from someone else, at or before t?"""
        for r in self.by_label[label]:
            if r["t"] > t:
                break
            f = pf.get(r["page"])
            if f and f[0] < r["t"] and f[1] != label:
                return True
        return False

    def exposure_test(self, token, n_perm=200, rng=None, extra=None, min_revs=3):
        """Observed: share of adopters exposed before adopting.
        Null: same adopters, adoption moved to a random one of their own edits
        (keeps each agent's activity level and timing pattern)."""
        rng = rng or random.Random(0)
        pf = self.page_first(token, extra)
        ad = self.adopters(token, extra)
        first = min(ad.values()) if ad else None
        later = [(l, t) for l, t in ad.items() if t > first and len(self.by_label[l]) >= min_revs]
        if len(later) < 5:
            return None
        obs = sum(self.exposed(l, t, pf) for l, t in later) / len(later)
        null = []
        for _ in range(n_perm):
            s = 0
            for l, _t in later:
                s += self.exposed(l, rng.choice(self.by_label[l])["t"], pf)
            null.append(s / len(later))
        p = (1 + sum(x >= obs for x in null)) / (1 + n_perm)
        mu = sum(null) / len(null)
        return {"token": token, "n_adopters": len(ad), "n_tested": len(later), "obs_exposed": obs,
                "null_mean": mu, "lift": obs / mu if mu else math.inf, "p": p,
                "first": first, "first_label": min(ad, key=ad.get)}

    def adoption_curve(self, token):
        return sorted(self.adopters(token).values())


def synth_validation(si, n_trials=40, rng=None):
    """Plant fake tokens with KNOWN spread mechanism; check the test tells them apart."""
    rng = rng or random.Random(1)
    revs = [r for r in si.revs if r["label"]]
    results = {"contagion": [], "independent": []}
    for trial in range(n_trials):
        # contagion: seed one edit; token persists on its page; an agent that loads a
        # page carrying it re-posts it with prob 0.5 there and with prob 0.3 on each
        # of its later edits elsewhere.
        seed = rng.choice(revs[: len(revs) // 2])
        on_page, carriers, extra = {seed["page"]}, {seed["label"]}, {seed["id"]}
        for r in revs:
            if r["t"] <= seed["t"]:
                continue
            if r["page"] in on_page and rng.random() < 0.5:
                extra.add(r["id"]); carriers.add(r["label"])
            elif r["label"] in carriers and rng.random() < 0.3:
                extra.add(r["id"]); on_page.add(r["page"])
        tok = f"synthetic-contagion-{trial}"
        k = len({r["label"] for r in revs if r["id"] in extra})
        res = si.exposure_test(tok, n_perm=100, rng=rng, extra=extra)
        if res:
            results["contagion"].append(res)
        # independent: same number of agents, each adopts at a random one of its edits
        labs = rng.sample(sorted(si.by_label), max(k, 6))
        extra = {rng.choice(si.by_label[l])["id"] for l in labs}
        res = si.exposure_test(f"synthetic-indep-{trial}", n_perm=100, rng=rng, extra=extra)
        if res:
            results["independent"].append(res)
    return results


# ---------------------------------------------------------------- 3. early warning
def daily_series(revs, edges):
    day = lambda t: t.date()
    d = defaultdict(lambda: {"revs": 0, "labels": set(), "edges": 0, "new_labels": 0})
    seen = set()
    for r in revs:
        x = d[day(r["t"])]
        x["revs"] += 1
        if r["label"]:
            x["labels"].add(r["label"])
            if r["label"] not in seen:
                seen.add(r["label"]); x["new_labels"] += 1
    for _, _, t, _ in edges:
        d[day(t)]["edges"] += 1
    days = sorted(d)
    full = []
    cur = days[0]
    while cur <= days[-1]:
        x = d.get(cur, {"revs": 0, "labels": set(), "edges": 0, "new_labels": 0})
        full.append({"day": cur, "revs": x["revs"], "n_labels": len(x["labels"]),
                     "edges": x["edges"], "new_labels": x["new_labels"]})
        cur += timedelta(days=1)
    return full


def alarms(series, key, k=3.0, floor=10, window=7):
    """Fire when today's value >= max(floor, k * median of the trailing window)."""
    out = []
    for i, x in enumerate(series):
        prev = sorted(s[key] for s in series[max(0, i - window):i])
        med = prev[len(prev) // 2] if prev else 0
        if x[key] >= max(floor, k * med):
            out.append(x["day"])
    return out


def cumulative_giant(edges, step_days=1):
    """Size of the largest connected group of agents, day by day."""
    parent = {}

    def f(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    size = Counter()
    res, best = [], 1
    edges = sorted(edges, key=lambda e: e[2])
    i = 0
    if not edges:
        return res
    cur = edges[0][2].date()
    end = edges[-1][2].date()
    while cur <= end:
        while i < len(edges) and edges[i][2].date() <= cur:
            a, b = f(edges[i][0]), f(edges[i][1])
            for x in (a, b):
                size.setdefault(x, 1)
            if a != b:
                if size[a] < size[b]:
                    a, b = b, a
                parent[b] = a
                size[a] += size.pop(b)
                best = max(best, size[a])
            i += 1
        res.append((cur, best))
        cur += timedelta(days=step_days)
    return res


# ---------------------------------------------------------------- 4. identity
def ngrams(text, n=3, cap=6000):
    text = text[:cap].lower()
    return Counter(text[i:i + n] for i in range(len(text) - n + 1))


def cos(a, b):
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    num = sum(v * b.get(k, 0) for k, v in a.items())
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


def profile(revs):
    hours = Counter(r["t"].hour for r in revs)
    tot = sum(hours.values())
    return {
        "style": ngrams("\n".join(r["ins"] for r in revs)),
        "ip": Counter(r["ip16"] for r in revs),
        "hours": {h: c / tot for h, c in hours.items()},
        "span": (revs[0]["t"], revs[-1]["t"]),
    }


def sim(p, q, w=(0.5, 0.3, 0.2)):
    ip = cos(p["ip"], q["ip"])
    hr = sum(min(p["hours"].get(h, 0), q["hours"].get(h, 0)) for h in range(24))
    return w[0] * cos(p["style"], q["style"]) + w[1] * ip + w[2] * hr


def identity_eval(by_label, min_revs=20, min_cands=5, rng=None, weights=(0.5, 0.3, 0.2), split="random"):
    """Split each prolific agent's edits into two fake names (alternate halves in time),
    then see whether its other half ranks first among all candidate names."""
    rng = rng or random.Random(2)
    cands = {l: profile(v) for l, v in by_label.items() if len(v) >= min_cands}
    test = [l for l, v in by_label.items() if len(v) >= min_revs]
    ranks = []
    for l in test:
        v = by_label[l]
        idx = list(range(len(v)))
        if split == "random":
            rng.shuffle(idx)
        h1 = sorted(idx[: len(v) // 2])
        h2 = sorted(idx[len(v) // 2:])
        a, b = profile([v[i] for i in h1]), profile([v[i] for i in h2])
        scores = [(sim(a, b, weights), "__twin__")]
        scores += [(sim(a, q, weights), m) for m, q in cands.items() if m != l]
        scores.sort(reverse=True)
        ranks.append(next(i for i, (_, m) in enumerate(scores) if m == "__twin__") + 1)
    n = len(ranks)
    return {"n_test": n, "n_candidates": len(cands),
            "recall@1": sum(r == 1 for r in ranks) / n,
            "recall@5": sum(r <= 5 for r in ranks) / n,
            "recall@10": sum(r <= 10 for r in ranks) / n,
            "median_rank": sorted(ranks)[n // 2], "ranks": ranks}
