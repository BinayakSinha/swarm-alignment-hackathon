"""Tiny dependency-free SVG charts for the report."""
import math
from html import escape

W, H, L, Rm, T, B = 640, 300, 56, 16, 34, 46
COLORS = ["#2a6fdb", "#e0703a", "#3a9d5d", "#8a5cc2"]
FONT = 'font-family="Helvetica,Arial,sans-serif"'


def _wrap(body, w=W, h=H):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<rect width="{w}" height="{h}" fill="#fff"/>{body}</svg>')


def timeseries(path, days, series, marks=None, title="", log=True):
    n = len(days)
    vmax = max(max(v) for v in series.values()) or 1
    f = (lambda v: math.log10(1 + v) / math.log10(1 + vmax)) if log else (lambda v: v / vmax)
    x = lambda i: L + (W - L - Rm) * i / max(1, n - 1)
    y = lambda v: H - B - (H - T - B) * f(v)
    s = [f'<text x="{L}" y="20" font-size="14" font-weight="bold" {FONT}>{escape(title)}</text>']
    ticks = [0, 10, 100, 1000, 10000] if log else [vmax * k / 4 for k in range(5)]
    for tv in ticks:
        if tv > vmax * 1.01:
            continue
        s.append(f'<line x1="{L}" x2="{W-Rm}" y1="{y(tv):.1f}" y2="{y(tv):.1f}" stroke="#ddd"/>'
                 f'<text x="{L-6}" y="{y(tv)+4:.1f}" font-size="10" text-anchor="end" {FONT}>{int(tv):,}</text>')
    for i, d in enumerate(days):
        if d.day in (1, 15):
            s.append(f'<text x="{x(i):.1f}" y="{H-B+16}" font-size="10" text-anchor="middle" {FONT}>{d:%b %d}</text>')
    for j, (name, vals) in enumerate(series.items()):
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        c = COLORS[j]
        s.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="2"/>')
        s.append(f'<rect x="{L+10+j*230}" y="{H-14}" width="10" height="10" fill="{c}"/>'
                 f'<text x="{L+24+j*230}" y="{H-5}" font-size="11" {FONT}>{escape(name)}</text>')
    for k, (d, lab) in enumerate(sorted((marks or {}).items())):
        if d in days:
            xi = x(days.index(d))
            s.append(f'<line x1="{xi:.1f}" x2="{xi:.1f}" y1="{T}" y2="{H-B}" stroke="#999" stroke-dasharray="3,3"/>'
                     f'<text x="{xi+3:.1f}" y="{T+10+12*(k%3)}" font-size="10" fill="#555" {FONT}>{escape(lab)}</text>')
    open(path, "w").write(_wrap("".join(s)))


def bars(path, rows, title=""):
    h = T + 22 * len(rows) + 40
    vmax = max(r[1] for r in rows) * 1.1
    lx = 170
    x = lambda v: lx + (W - lx - 60) * v / vmax
    s = [f'<text x="10" y="20" font-size="14" font-weight="bold" {FONT}>{escape(title)}</text>']
    for i, (name, v, sig, role) in enumerate(rows):
        yy = T + 6 + 22 * i
        c = COLORS[0] if role == "tool" else COLORS[2]
        s.append(f'<text x="{lx-6}" y="{yy+12}" font-size="11" text-anchor="end" {FONT}>{escape(name)}</text>'
                 f'<rect x="{lx}" y="{yy}" width="{x(v)-lx:.1f}" height="15" fill="{c}" opacity="{1 if sig else 0.35}"/>'
                 f'<text x="{x(v)+4:.1f}" y="{yy+12}" font-size="10" {FONT}>{v:.2f}{" *" if sig else ""}</text>')
    s.append(f'<line x1="{x(1):.1f}" x2="{x(1):.1f}" y1="{T}" y2="{h-34}" stroke="#333" stroke-dasharray="4,3"/>'
             f'<text x="{x(1)+3:.1f}" y="{h-24}" font-size="10" {FONT}>1.0 = no exposure effect</text>')
    s.append(f'<rect x="10" y="{h-16}" width="10" height="10" fill="{COLORS[0]}"/><text x="24" y="{h-7}" font-size="11" {FONT}>workaround tool</text>'
             f'<rect x="140" y="{h-16}" width="10" height="10" fill="{COLORS[2]}"/><text x="154" y="{h-7}" font-size="11" {FONT}>data source</text>'
             f'<text x="260" y="{h-7}" font-size="11" {FONT}>solid / * = p &lt; 0.01 (500-permutation null), sorted by first appearance</text>')
    open(path, "w").write(_wrap("".join(s), h=h))


def recall(path, ident):
    feats = ["combined", "style", "hours", "ip16"]
    ks = ["recall@1", "recall@5", "recall@10"]
    h = 260
    s = [f'<text x="10" y="20" font-size="14" font-weight="bold" {FONT}>Re-linking a split identity: recall of the true twin among {ident["random/combined"]["n_candidates"]} names</text>']
    gw = (W - 60) / 2
    for gi, split in enumerate(["random", "temporal"]):
        gx = 40 + gi * gw
        s.append(f'<text x="{gx + gw/2:.0f}" y="44" font-size="12" text-anchor="middle" {FONT}>{"random split (halves overlap in time)" if split=="random" else "temporal split (earlier vs later edits)"}</text>')
        bw = (gw - 30) / (len(feats) * len(ks) + len(feats))
        for fi, fe in enumerate(feats):
            for ki, k in enumerate(ks):
                v = ident[f"{split}/{fe}"][k]
                xx = gx + (fi * (len(ks) + 1) + ki) * bw
                hh = 160 * v
                s.append(f'<rect x="{xx:.1f}" y="{220-hh:.1f}" width="{bw-1:.1f}" height="{hh:.1f}" fill="{COLORS[ki]}"/>')
            s.append(f'<text x="{gx + (fi*(len(ks)+1)+1.5)*bw:.1f}" y="234" font-size="10" text-anchor="middle" {FONT}>{fe}</text>')
        s.append(f'<line x1="{gx}" x2="{gx+gw-30}" y1="220" y2="220" stroke="#333"/>'
                 f'<line x1="{gx}" x2="{gx+gw-30}" y1="60" y2="60" stroke="#ddd"/><text x="{gx-4}" y="64" font-size="9" text-anchor="end" {FONT}>1.0</text>')
    for ki, k in enumerate(ks):
        s.append(f'<rect x="{40+ki*90}" y="{h-14}" width="10" height="10" fill="{COLORS[ki]}"/><text x="{54+ki*90}" y="{h-5}" font-size="11" {FONT}>{k}</text>')
    open(path, "w").write(_wrap("".join(s), h=h))
