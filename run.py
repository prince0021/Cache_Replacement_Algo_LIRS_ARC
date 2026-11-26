#!/usr/bin/env python3
"""CLI entry point: python run.py gen | test | sizing | experiments | ui | all"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import config as cfg


def cmd_gen(args) -> None:
    """Generate all traces."""
    from cachesim.traces import generate_all

    capacity = cfg.get_capacity(args)
    n_refs = cfg.get_n_refs(args)
    print(f"Generating traces: C={capacity}, N={n_refs}")
    t0 = time.perf_counter()
    manifest = generate_all(capacity, n_refs, cfg.TRACES_DIR, cfg.EXT_TRACES_DIR)
    elapsed = time.perf_counter() - t0
    print(f"\nDone: {len(manifest)} traces in {elapsed:.1f}s")
    print(f"Next: python run.py test")

    from cachesim.logbook import log_event
    log_event("gen", {"capacity": capacity, "n_refs": n_refs,
                       "trace_count": len(manifest)})


def cmd_test(args) -> None:
    """Run the pytest suite."""
    print("Running pytest...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=cfg.PROJECT_ROOT,
    )
    from cachesim.logbook import log_event
    log_event("test", {"exit_code": result.returncode})
    if result.returncode == 0:
        print(f"\nNext: python run.py sizing")
    else:
        print("\nTests failed — fix before continuing.")


def cmd_sizing(args) -> None:
    """Run the sizing study."""
    from cachesim.sizing import run_sizing_study
    capacity = cfg.get_capacity(args)
    print(f"Running sizing study at C={capacity}...")
    t0 = time.perf_counter()
    run_sizing_study(capacity)
    elapsed = time.perf_counter() - t0
    print(f"\nSizing study done in {elapsed:.1f}s")
    print(f"Next: python run.py experiments")

    from cachesim.logbook import log_event
    log_event("sizing", {"capacity": capacity, "elapsed_s": round(elapsed, 1)})


def cmd_experiments(args) -> None:
    """Run all experiments."""
    from cachesim.engine import run_all_experiments
    capacity = cfg.get_capacity(args)
    n_refs = cfg.get_n_refs(args)
    sets = cfg.get_sets(args)
    ways = cfg.get_ways(args)
    small = getattr(args, "small", False)
    replicates = getattr(args, "replicates", 1)
    print(f"Running experiments: C={capacity}, sets={sets}x{ways}, N={n_refs}")
    t0 = time.perf_counter()
    run_all_experiments(capacity, sets, ways, n_refs, small=small,
                        replicates=replicates)
    elapsed = time.perf_counter() - t0
    print(f"\nExperiments done in {elapsed:.1f}s")
    print(f"Next: python run.py ui")

    from cachesim.logbook import log_event
    log_event("experiments", {"capacity": capacity, "elapsed_s": round(elapsed, 1)})


def cmd_ui(args) -> None:
    """Launch Streamlit UI."""
    print("Launching Streamlit app...")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.headless", "true"],
        cwd=cfg.PROJECT_ROOT,
    )


def cmd_all(args) -> None:
    """Run gen, test, sizing, experiments."""
    for fn in [cmd_gen, cmd_test, cmd_sizing, cmd_experiments]:
        fn(args)
        print()
    # Summary
    print("=" * 60)
    print("ALL DONE")
    print("=" * 60)
    results_latest = cfg.RESULTS_DIR / "latest.csv"
    if results_latest.exists():
        import pandas as pd
        df = pd.read_csv(results_latest)
        print(f"Results: {len(df)} rows in {results_latest}")
    print(f"\nLaunch the UI: python run.py ui")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache simulation project CLI")
    cfg._add_common_args(parser)
    parser.add_argument("--replicates", type=int, default=1,
                        help="Replicates for variance study")
    parser.add_argument("command", choices=["gen", "test", "sizing",
                                            "experiments", "ui", "all"])
    args = parser.parse_args()

    dispatch = {
        "gen": cmd_gen,
        "test": cmd_test,
        "sizing": cmd_sizing,
        "experiments": cmd_experiments,
        "ui": cmd_ui,
        "all": cmd_all,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
