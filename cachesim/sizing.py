"""Sizing study — prove the chosen N is large enough.

For representative traces, run fast policies on increasing prefix lengths
with multiple seeds and check convergence.
"""
from __future__ import annotations

import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config as cfg
from cachesim.traces import gen_zipf, gen_loop, gen_scanhot
from cachesim.policies import get_policy


PREFIX_LENGTHS = [20_000, 50_000, 100_000, 200_000, 400_000, 800_000, 1_600_000]
N_SEEDS = 5
FAST_POLICIES = ["LRU", "ARC", "SRRIP", "DRRIP", "LIRS"]

REPRESENTATIVE_TRACES = [
    ("zipf_a0.4_ws2C", "zipf", {"alpha": 0.4, "ws_mult": 2.0}),
    ("zipf_a0.4_ws10C", "zipf", {"alpha": 0.4, "ws_mult": 10.0}),
    ("zipf_a1.0_ws2C", "zipf", {"alpha": 1.0, "ws_mult": 2.0}),
    ("zipf_a1.0_ws10C", "zipf", {"alpha": 1.0, "ws_mult": 10.0}),
    ("zipf_a1.4_ws2C", "zipf", {"alpha": 1.4, "ws_mult": 2.0}),
    ("zipf_a1.4_ws10C", "zipf", {"alpha": 1.4, "ws_mult": 10.0}),
    ("loop_1.10C", "loop", {"loop_mult": 1.10}),
    ("scanhot_h0.5C_s3C", "scanhot", {"hot_mult": 0.5, "scan_mult": 3}),
]


def _gen_trace(trace_info: dict, capacity: int, n_refs: int, seed: int) -> np.ndarray:
    family = trace_info[1]
    params = trace_info[2]
    if family == "zipf":
        n_blocks = max(1, int(params["ws_mult"] * capacity))
        return gen_zipf(n_blocks, n_refs, params["alpha"], seed)
    elif family == "loop":
        loop_size = max(1, int(params["loop_mult"] * capacity))
        return gen_loop(loop_size, n_refs)
    elif family == "scanhot":
        hot_size = int(params["hot_mult"] * capacity)
        scan_size = int(params["scan_mult"] * capacity)
        return gen_scanhot(hot_size, scan_size, capacity, n_refs,
                           f"sizing_{seed}")
    raise ValueError(f"Unknown family {family}")


def _run_policy(name: str, capacity: int, trace: list) -> float:
    cls = get_policy(name)
    if name == "SRRIP":
        p = cls(capacity, ways=cfg.WAYS, sets=cfg.SETS)
    elif name == "DRRIP":
        p = cls(capacity, ways=cfg.WAYS, sets=cfg.SETS,
                leader_sets=cfg.DRRIP_LEADER_SETS)
    else:
        p = cls(capacity)
    for key in trace:
        p.access(key)
    return p.hit_ratio


def _compulsory_share(trace: list) -> float:
    seen = set()
    compulsory = 0
    for k in trace:
        if k not in seen:
            compulsory += 1
            seen.add(k)
    return compulsory / len(trace) if trace else 0.0


def run_sizing_study(capacity: int) -> pd.DataFrame:
    cfg.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    base_seed = cfg.BASE_SEED

    total_jobs = (len(REPRESENTATIVE_TRACES) * len(PREFIX_LENGTHS) *
                  N_SEEDS * len(FAST_POLICIES))
    done = 0
    t0 = time.perf_counter()

    for trace_info in REPRESENTATIVE_TRACES:
        trace_name = trace_info[0]
        for plen in PREFIX_LENGTHS:
            for s in range(N_SEEDS):
                seed = base_seed + s * 1000 + hash(trace_name) % 10000
                trace = _gen_trace(trace_info, capacity, plen, seed).tolist()
                comp_share = _compulsory_share(trace)

                for policy_name in FAST_POLICIES:
                    hr = _run_policy(policy_name, capacity, trace)
                    records.append({
                        "trace": trace_name,
                        "prefix_length": plen,
                        "seed": seed,
                        "policy": policy_name,
                        "hit_ratio": hr,
                        "compulsory_share": comp_share,
                    })
                    done += 1

            elapsed = time.perf_counter() - t0
            if done > 0:
                eta = elapsed / done * (total_jobs - done)
                if eta > 900:  # cap at 15 min
                    print(f"  Warning: ETA {eta:.0f}s > 900s, reducing seeds")

        print(f"  {trace_name}: done ({done}/{total_jobs})")

    df = pd.DataFrame(records)
    df.to_csv(cfg.RESULTS_DIR / "sizing_study.csv", index=False)

    # Compute summary
    summary = df.groupby(["trace", "prefix_length", "policy"]).agg(
        mean_hr=("hit_ratio", "mean"),
        std_hr=("hit_ratio", "std"),
    ).reset_index()

    # Find convergence: smallest N where mean is within 0.2pp of value at largest N
    max_plen = max(PREFIX_LENGTHS)
    max_vals = summary[summary["prefix_length"] == max_plen][
        ["trace", "policy", "mean_hr"]
    ].rename(columns={"mean_hr": "max_hr"})
    merged = summary.merge(max_vals, on=["trace", "policy"])
    merged["diff_pp"] = abs(merged["mean_hr"] - merged["max_hr"]) * 100

    converged = merged[merged["diff_pp"] <= 0.2]
    if len(converged) > 0:
        conv_by_tp = converged.groupby(["trace", "policy"])["prefix_length"].min()
        recommended_n = int(conv_by_tp.max())
    else:
        recommended_n = max_plen

    print(f"\n  Recommended N: {recommended_n:,}")
    if recommended_n != cfg.N_REFS:
        print(f"  (Current config N_REFS={cfg.N_REFS:,} — consider updating)")

    # Generate figure
    _plot_sizing(summary, cfg.RESULTS_DIR / "sizing_study.png")
    print(f"  Figure saved: results/sizing_study.png")

    return df


def _plot_sizing(summary: pd.DataFrame, path: Path) -> None:
    traces = summary["trace"].unique()
    fig, axes = plt.subplots(2, 4, figsize=(20, 8), squeeze=False)
    for idx, trace in enumerate(traces):
        ax = axes[idx // 4][idx % 4]
        sub = summary[summary["trace"] == trace]
        for policy in FAST_POLICIES:
            ps = sub[sub["policy"] == policy]
            ax.errorbar(ps["prefix_length"], ps["mean_hr"] * 100,
                        yerr=ps["std_hr"] * 100, label=policy,
                        marker="o", markersize=3, capsize=2)
        ax.set_title(trace, fontsize=9)
        ax.set_xlabel("Prefix length")
        ax.set_ylabel("Hit ratio %")
        ax.set_xscale("log")
        ax.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()
