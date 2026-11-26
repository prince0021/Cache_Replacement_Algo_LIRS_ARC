"""Chart helpers for the Streamlit UI — one function per chart type."""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# ── Colour palette: cool = software, warm = hardware, grey = baseline ──
POLICY_COLORS = {
    "LRU": "#888888",
    "FIFO": "#aaaaaa",
    "OPT": "#444444",
    "ARC": "#1f77b4",
    "LIRS": "#2ca02c",
    "CLOCK-Pro": "#17becf",
    "CAR": "#9467bd",
    "MQ": "#7f7f7f",
    "LRU-K": "#8c564b",
    "SA-LRU": "#bcbd22",
    "SRRIP": "#d62728",
    "BRRIP": "#ff7f0e",
    "DRRIP": "#e377c2",
}


def summary_table(df: pd.DataFrame, metric: str = "hit_ratio") -> pd.DataFrame:
    """Pivot trace x policy, highlight best per row."""
    pivot = df.pivot_table(index="trace", columns="policy", values=metric)
    return (pivot * 100).round(2)


def heatmap_alpha_ws(df: pd.DataFrame, policy: str,
                     manifest: pd.DataFrame) -> go.Figure:
    zipf = df[df["trace"].str.startswith("zipf_")]
    merged = zipf.merge(manifest[["name", "alpha", "ws_multiplier"]],
                        left_on="trace", right_on="name")
    sub = merged[merged["policy"] == policy]
    pivot = sub.pivot_table(index="alpha", columns="ws_multiplier",
                            values="hit_ratio") * 100
    fig = px.imshow(pivot, text_auto=".1f", aspect="auto",
                    labels=dict(x="Working-set multiplier", y="Alpha",
                                color="Hit ratio %"),
                    title=f"{policy} hit ratio by alpha and working-set size")
    return fig


def diff_heatmap(df: pd.DataFrame, pol_a: str, pol_b: str,
                 manifest: pd.DataFrame) -> go.Figure:
    zipf = df[df["trace"].str.startswith("zipf_")]
    merged = zipf.merge(manifest[["name", "alpha", "ws_multiplier"]],
                        left_on="trace", right_on="name")
    a = merged[merged["policy"] == pol_a].set_index(["alpha", "ws_multiplier"])["hit_ratio"]
    b = merged[merged["policy"] == pol_b].set_index(["alpha", "ws_multiplier"])["hit_ratio"]
    diff = ((a - b) * 100).reset_index()
    diff.columns = ["alpha", "ws_multiplier", "diff"]
    pivot = diff.pivot_table(index="alpha", columns="ws_multiplier", values="diff")
    fig = px.imshow(pivot, text_auto=".1f", aspect="auto",
                    color_continuous_midpoint=0,
                    color_continuous_scale="RdBu_r",
                    labels=dict(x="Working-set multiplier", y="Alpha",
                                color="Diff (pp)"),
                    title=f"{pol_a} minus {pol_b} (percentage points)")
    return fig


def hr_vs_alpha(df: pd.DataFrame, ws_mult: float,
                manifest: pd.DataFrame) -> go.Figure:
    zipf = df[df["trace"].str.startswith("zipf_")]
    merged = zipf.merge(manifest[["name", "alpha", "ws_multiplier"]],
                        left_on="trace", right_on="name")
    sub = merged[merged["ws_multiplier"] == ws_mult]
    fig = px.line(sub, x="alpha", y=sub["hit_ratio"] * 100,
                  color="policy", markers=True,
                  color_discrete_map=POLICY_COLORS,
                  labels={"y": "Hit ratio %", "alpha": "Zipf alpha"},
                  title=f"Hit ratio vs alpha (W={ws_mult}C)")
    return fig


def loop_bar(df: pd.DataFrame) -> go.Figure:
    loops = df[df["trace"].str.startswith("loop_")]
    fig = px.bar(loops, x="trace", y=loops["hit_ratio"] * 100,
                 color="policy", barmode="group",
                 color_discrete_map=POLICY_COLORS,
                 labels={"y": "Hit ratio %"},
                 title="Loop traces")
    # Add OPT ceiling
    opt = loops[loops["policy"] == "OPT"]
    if not opt.empty:
        for _, row in opt.iterrows():
            fig.add_hline(y=row["hit_ratio"] * 100, line_dash="dash",
                          annotation_text=f"OPT {row['trace']}", line_color="grey")
    return fig


def scan_bar(df: pd.DataFrame) -> go.Figure:
    scans = df[df["trace"].str.startswith("scanhot")]
    fig = px.bar(scans, x="trace", y=scans["hit_ratio"] * 100,
                 color="policy", barmode="group",
                 color_discrete_map=POLICY_COLORS,
                 labels={"y": "Hit ratio %"},
                 title="Scan-hot traces")
    return fig


def miss_ratio_curve(df: pd.DataFrame, trace_name: str) -> go.Figure:
    sub = df[df["trace"] == trace_name].sort_values("capacity")
    fig = px.line(sub, x="capacity", y=(1 - sub["hit_ratio"]) * 100,
                  color="policy", markers=True,
                  color_discrete_map=POLICY_COLORS,
                  labels={"y": "Miss ratio %", "capacity": "Cache capacity"},
                  title=f"Miss-ratio curve: {trace_name}")
    return fig


def throughput_bar(df: pd.DataFrame) -> go.Figure:
    avg = df.groupby("policy")["refs_per_second"].mean().reset_index()
    fig = px.bar(avg, x="policy", y="refs_per_second",
                 color="policy", color_discrete_map=POLICY_COLORS,
                 title="Average throughput (refs/s)")
    return fig
