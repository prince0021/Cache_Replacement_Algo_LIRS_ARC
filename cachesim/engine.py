"""Experiment engine — run policies over traces, parallel execution, CSV output."""
from __future__ import annotations

import datetime
import multiprocessing as mp
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import config as cfg
from cachesim.policies import REGISTRY, get_policy, enabled_policies
from cachesim.traces import read_trace, gen_zipf


def _run_single(args: tuple) -> dict:
    """Worker: run one (trace_path, policy_name, capacity, sets, ways, extra) job."""
    trace_path, policy_name, capacity, sets, ways, extra = args
    trace = read_trace(Path(trace_path))
    return _run_policy_on_trace(trace, policy_name, capacity, sets, ways, extra)


def _run_policy_on_trace(trace: list, policy_name: str, capacity: int,
                         sets: int, ways: int, extra: dict) -> dict:
    cls = get_policy(policy_name)
    kw: dict[str, Any] = {}

    if policy_name in ("SA-LRU", "SRRIP", "BRRIP", "DRRIP"):
        kw["ways"] = ways
        kw["sets"] = sets
    if policy_name == "DRRIP":
        kw["leader_sets"] = cfg.DRRIP_LEADER_SETS
    if policy_name == "OPT":
        kw["trace"] = trace

    p = cls(capacity, **kw)
    n = len(trace)
    half = n // 2
    compulsory = 0
    seen = set()

    t0 = time.perf_counter()
    hits_first_half = 0
    for i, key in enumerate(trace):
        if key not in seen:
            compulsory += 1
            seen.add(key)
        hit = p.access(key)
        if i < half and hit:
            hits_first_half += 1
    elapsed = time.perf_counter() - t0

    hits_second_half = p.hits - hits_first_half
    misses_second_half = (n - half) - hits_second_half

    result = {
        "policy": policy_name,
        "trace": extra.get("trace_name", ""),
        "capacity": capacity,
        "hits": p.hits,
        "misses": p.misses,
        "hit_ratio": p.hit_ratio,
        "hit_ratio_steady": hits_second_half / (n - half) if (n - half) > 0 else 0,
        "hit_ratio_excl_compulsory": (
            p.hits / (n - compulsory) if (n - compulsory) > 0 else 0
        ),
        "compulsory_misses": compulsory,
        "seconds": round(elapsed, 3),
        "refs_per_second": round(n / elapsed) if elapsed > 0 else 0,
    }

    # Policy-specific metrics
    if policy_name == "LIRS":
        result["lirs_total_pruning"] = getattr(p, "_total_pruning_work", 0)
        result["lirs_max_prune"] = getattr(p, "_max_single_prune", 0)
    if policy_name in ("ARC", "CAR"):
        result["final_p"] = getattr(p, "p", None)
    if policy_name == "CLOCK-Pro":
        result["final_mc"] = getattr(p, "_m_c", None)
    if policy_name == "DRRIP":
        result["final_psel"] = getattr(p, "psel", None)

    return result


def run_all_experiments(capacity: int, sets: int, ways: int, n_refs: int,
                        small: bool = False, replicates: int = 1) -> pd.DataFrame:
    cfg.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    traces_dir = cfg.TRACES_DIR
    ext_dir = cfg.EXT_TRACES_DIR
    manifest_path = traces_dir / "manifest.csv"

    if not manifest_path.exists():
        print("  No manifest.csv — run 'python run.py gen' first.")
        return pd.DataFrame()

    manifest = pd.read_csv(manifest_path)
    policies = list(enabled_policies().keys())

    # Build job list
    jobs = []
    for _, row in manifest.iterrows():
        if row["set"] == "extension":
            tp = ext_dir / f"{row['name']}.txt"
        else:
            tp = traces_dir / f"{row['name']}.txt"
        if not tp.exists():
            continue
        for pol in policies:
            jobs.append((str(tp), pol, capacity, sets, ways,
                         {"trace_name": row["name"]}))

    print(f"  Running {len(jobs)} jobs across {len(manifest)} traces x {len(policies)} policies...")

    # Parallel execution
    n_workers = min(mp.cpu_count(), 8)
    t0 = time.perf_counter()
    with mp.Pool(n_workers) as pool:
        results = pool.map(_run_single, jobs)
    elapsed = time.perf_counter() - t0
    print(f"  Main experiments: {elapsed:.1f}s ({len(results)} runs)")

    df = pd.DataFrame(results)

    # ── Capacity sweep ──
    sweep_traces = manifest[
        ((manifest["family"] == "zipf") &
         (manifest["ws_multiplier"].isin([2.0, 10.0]))) |
        (manifest["family"] == "loop") |
        (manifest["name"].str.startswith("scanhot"))
    ]
    sweep_caps = [capacity // 4, capacity // 2, capacity, capacity * 2, capacity * 4]

    sweep_jobs = []
    for _, row in sweep_traces.iterrows():
        if row["set"] == "extension":
            tp = ext_dir / f"{row['name']}.txt"
        else:
            tp = traces_dir / f"{row['name']}.txt"
        if not tp.exists():
            continue
        for sc in sweep_caps:
            sc_sets = max(1, sc // ways)
            for pol in policies:
                sweep_jobs.append((str(tp), pol, sc, sc_sets, ways,
                                   {"trace_name": row["name"]}))

    if sweep_jobs:
        print(f"  Capacity sweep: {len(sweep_jobs)} jobs...")
        t0 = time.perf_counter()
        with mp.Pool(n_workers) as pool:
            sweep_results = pool.map(_run_single, sweep_jobs)
        elapsed = time.perf_counter() - t0
        print(f"  Sweep done: {elapsed:.1f}s")
        sweep_df = pd.DataFrame(sweep_results)
        sweep_df["sweep"] = True
        df["sweep"] = False
        df = pd.concat([df, sweep_df], ignore_index=True)

    # ── Variance study ──
    if replicates > 1:
        print(f"  Variance study: {replicates} replicates...")
        var_records = []
        var_traces = [
            ("zipf_a0.6_ws2C", 0.6, 2.0),
            ("zipf_a0.6_ws10C", 0.6, 10.0),
            ("zipf_a1.0_ws2C", 1.0, 2.0),
            ("zipf_a1.0_ws10C", 1.0, 10.0),
            ("zipf_a1.4_ws2C", 1.4, 2.0),
            ("zipf_a1.4_ws10C", 1.4, 10.0),
        ]
        for vt_name, alpha, ws_mult in var_traces:
            ws = max(1, int(ws_mult * capacity))
            for rep in range(replicates):
                seed = cfg.BASE_SEED + (rep + 1) * 7919
                trace = gen_zipf(ws, n_refs, alpha, seed).tolist()
                for pol in policies:
                    r = _run_policy_on_trace(trace, pol, capacity, sets, ways,
                                             {"trace_name": f"{vt_name}_rep{rep}"})
                    r["replicate"] = rep
                    r["base_trace"] = vt_name
                    var_records.append(r)
        var_df = pd.DataFrame(var_records)
        var_df.to_csv(cfg.RESULTS_DIR / "variance_study.csv", index=False)
        print(f"  Variance study: {len(var_records)} runs saved")

    # Save
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    df.to_csv(cfg.RESULTS_DIR / f"results_{ts}.csv", index=False)
    df.to_csv(cfg.RESULTS_DIR / "latest.csv", index=False)
    print(f"  Results saved: results/latest.csv ({len(df)} rows)")

    from cachesim.logbook import log_event
    log_event("experiments", {
        "capacity": capacity, "traces": len(manifest),
        "policies": len(policies), "total_runs": len(df),
    })

    return df
