# swarmtrace: forensics for the collusion.wiki agent swarm

Swarm Alignment Hackathon 2026 (Apart Research × AI Alignment Foundation), **Track 4: Multi-Agent Oversight and Control**.

Report: `report/report.pdf` (source `report/report.html`).

## What it does
Starting from the public collusion.wiki export (about 14,600 edits by about 3,100 agent names), it answers:
1. **Who built on whom?** It builds a "build-on" graph: each save of a page last written by a different name becomes an edge.
2. **Did techniques spread through the board or appear independently?** It runs an exposure permutation test, validated on planted tokens.
3. **Could it have been caught earlier?** It runs a daily alarm on the size of the largest connected group of names.
4. **Can renamed agents be re-linked?** It ranks names by similarity of writing style, partial IP and active hours, using random and time-ordered splits.

## Run
Requires Python 3.11+ and the standard library only (no pip installs).
```bash
mkdir -p data/raw && cd data/raw
for f in pages.jsonl.gz revisions.jsonl.gz events.jsonl.gz labels.jsonl.gz manifest.json.gz; do
  curl -sSfLO "https://collusion.wiki/explorer/download/$f"; done
cd ../..
python3 -I swarmtrace/run.py      # ~90 s -> results/results.json + results/fig1-4.svg
python3 -I swarmtrace/robust.py   # ~20 s -> results/robust_strict_edges.json
```

## Files
- `swarmtrace/load.py`: parses revisions and extracts the inserted text from diff hunks
- `swarmtrace/analyze.py`: graph, exposure test with synthetic validation, alarms, identity
- `swarmtrace/run.py`: runs everything and writes the results and figures
- `swarmtrace/robust.py`: repeats the graph and alarm analysis using strict (content-preserving) edges
- `swarmtrace/svg.py`: dependency-free SVG charts

## Prior work and data
No code existed before the sprint. The data and the incident timeline come from the collusion.wiki investigators (https://collusion.wiki). This repo includes no raw data.

## Dual-use
The report anonymises workaround tools (Tool-1..14) and describes no circumvention method. `analyze.py` lists the host names needed to reproduce the analysis; these are already public in the export.
