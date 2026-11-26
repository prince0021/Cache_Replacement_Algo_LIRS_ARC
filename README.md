# Cache Replacement Simulation Project

Simulator for 8 replacement algorithms (ARC, LIRS, CLOCK-Pro, CAR, MQ, LRU-K, SRRIP, DRRIP), 48 synthetic traces, a Streamlit dashboard, and teaching documents.

## Quick start

```bash
pip install -r requirements.txt
python run.py all
streamlit run app.py
```

`run.py all` generates traces, runs tests, performs the sizing study, and runs experiments. The Streamlit app then lets you explore results, step through algorithms, and export figures.

## Folder map

```
config.py          — all sizes, seeds, paths
run.py             — CLI: gen | test | sizing | experiments | ui | all
cachesim/policies/ — one file per algorithm, self-registering
cachesim/traces.py — generators, reader/writer, analysis
cachesim/engine.py — parallel experiment runner
cachesim/sizing.py — trace-length convergence study
app.py             — Streamlit UI (7 pages)
tests/             — pytest suite (62 tests, hand-derived expected values)
traces/            — 40 core + 8 extension traces + manifest.csv
results/           — experiment CSVs, sizing study
docs/              — UNDERSTANDING.md, MANUAL_TRACING_GUIDE.md, ANSWER_KEY.md, REPORT_MAPPING.md
```
