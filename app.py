"""Streamlit app — cache replacement simulation dashboard.

Launch: streamlit run app.py
"""
from __future__ import annotations

import subprocess
import sys
import io
import zipfile
from pathlib import Path

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as cfg
from cachesim.policies import REGISTRY, badge, enabled_policies
from cachesim.policies.base import Policy
from cachesim.traces import read_trace, trace_stats
import app_charts as charts

st.set_page_config(page_title="Cache Replacement Simulator", layout="wide")

# ── Small-mode detection ──────────────────────────────────────────────
IS_SMALL = False
if (cfg.RESULTS_DIR / "latest.csv").exists():
    _latest = pd.read_csv(cfg.RESULTS_DIR / "latest.csv", nrows=1)
    if not _latest.empty and _latest.iloc[0].get("capacity", cfg.CAPACITY) == cfg.SMALL_CAPACITY:
        IS_SMALL = True


# ═══════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════

def sidebar():
    st.sidebar.title("Cache Simulator")
    page = st.sidebar.radio("Page", [
        "1. Start here",
        "2. Datasets",
        "3. Run experiments",
        "4. Results",
        "5. Manual tracing",
        "6. Verification",
        "7. Sizing & confidence",
    ])

    # Status panel
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Status**")

    manifest_path = cfg.TRACES_DIR / "manifest.csv"
    n_traces = 0
    if manifest_path.exists():
        n_traces = len(pd.read_csv(manifest_path))
    st.sidebar.write(f"Traces: {n_traces}/48")

    tests_passed = "never run"
    st.sidebar.write(f"Tests: {tests_passed}")

    if (cfg.RESULTS_DIR / "latest.csv").exists():
        st.sidebar.write("Experiments: latest.csv present")
    else:
        st.sidebar.write("Experiments: not run")

    cap = cfg.SMALL_CAPACITY if IS_SMALL else cfg.CAPACITY
    n_refs = cfg.SMALL_N_REFS if IS_SMALL else cfg.N_REFS
    st.sidebar.write(f"Cache capacity: {cap}")
    st.sidebar.write(f"Trace length: {n_refs:,}")

    if IS_SMALL:
        st.sidebar.error("SMALL MODE: not for the report")

    # Policies panel
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Policies**")
    for name in cfg.ENABLED_POLICIES:
        b = badge(name)
        st.sidebar.write(f"- {name}: {b}")
    for name, reason in cfg.DROPPED_POLICIES.items():
        st.sidebar.write(f"- ~~{name}~~: {reason}")

    return page


# ═══════════════════════════════════════════════════════════════════════
# PAGE 1: START HERE
# ═══════════════════════════════════════════════════════════════════════

def page_start():
    st.header("Getting started")
    st.write("Follow these numbered steps in order. Each one builds on the previous.")

    if IS_SMALL:
        st.warning("SMALL MODE active — results are not for the report.")

    # Step 1
    st.subheader("Step 1: Generate datasets")
    st.write("Create 48 synthetic trace files (32 Zipfian, 4 scan, 4 loop, 8 extension).")
    has_traces = (cfg.TRACES_DIR / "manifest.csv").exists()
    if has_traces:
        st.success("Traces generated!")
    if st.button("Generate datasets", key="gen"):
        with st.spinner("Generating traces..."):
            from cachesim.traces import generate_all
            cap = cfg.SMALL_CAPACITY if IS_SMALL else cfg.CAPACITY
            n = cfg.SMALL_N_REFS if IS_SMALL else cfg.N_REFS
            generate_all(cap, n, cfg.TRACES_DIR, cfg.EXT_TRACES_DIR)
        st.success("Done!")
        st.rerun()

    # Step 2
    st.subheader("Step 2: Verify the simulator")
    st.write("Run the pytest suite to confirm all hand-derived tests pass.")
    if st.button("Run tests", key="test"):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
            capture_output=True, text=True, cwd=str(cfg.PROJECT_ROOT),
        )
        st.code(result.stdout + result.stderr)

    # Step 3
    st.subheader("Step 3: Check trace length (sizing study)")
    st.write("Prove that the chosen trace length N is large enough for stable results.")
    if not has_traces:
        st.info("Generate datasets first (Step 1).")
    elif st.button("Run sizing study", key="sizing"):
        with st.spinner("Running sizing study (may take a few minutes)..."):
            from cachesim.sizing import run_sizing_study
            cap = cfg.SMALL_CAPACITY if IS_SMALL else cfg.CAPACITY
            run_sizing_study(cap)
        st.success("Done! See the Sizing & confidence page.")

    # Step 4
    st.subheader("Step 4: Run experiments")
    st.write("Run all policies over all traces to generate results.")
    if not has_traces:
        st.info("Generate datasets first (Step 1).")
    elif st.button("Run experiments", key="exp"):
        with st.spinner("Running experiments..."):
            from cachesim.engine import run_all_experiments
            cap = cfg.SMALL_CAPACITY if IS_SMALL else cfg.CAPACITY
            sets = cfg.SMALL_SETS if IS_SMALL else cfg.SETS
            ways = cfg.SMALL_WAYS if IS_SMALL else cfg.WAYS
            n = cfg.SMALL_N_REFS if IS_SMALL else cfg.N_REFS
            run_all_experiments(cap, sets, ways, n)
        st.success("Done!")
        st.rerun()

    # Step 5
    st.subheader("Step 5: Look at results")
    st.write("Go to the Results page to explore hit ratios, heatmaps, and charts.")

    # Step 6
    st.subheader("Step 6: Practise manual tracing")
    st.write("Go to the Manual tracing page to step through algorithms.")


# ═══════════════════════════════════════════════════════════════════════
# PAGE 2: DATASETS
# ═══════════════════════════════════════════════════════════════════════

def page_datasets():
    st.header("Datasets")
    manifest_path = cfg.TRACES_DIR / "manifest.csv"
    if not manifest_path.exists():
        st.warning("No traces yet — run Step 1 on the Start page.")
        return

    manifest = pd.read_csv(manifest_path)

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        set_filter = st.selectbox("Set", ["all"] + sorted(manifest["set"].unique().tolist()))
    with col2:
        family_filter = st.selectbox("Family", ["all"] + sorted(manifest["family"].unique().tolist()))
    with col3:
        alpha_filter = st.selectbox("Alpha", ["all"] + sorted(
            [str(a) for a in manifest["alpha"].dropna().unique()]))

    filtered = manifest.copy()
    if set_filter != "all":
        filtered = filtered[filtered["set"] == set_filter]
    if family_filter != "all":
        filtered = filtered[filtered["family"] == family_filter]
    if alpha_filter != "all":
        filtered = filtered[filtered["alpha"] == float(alpha_filter)]

    st.dataframe(filtered[["name", "set", "family", "alpha", "ws_multiplier",
                           "n_refs", "n_unique", "estimated_alpha", "description"]],
                 use_container_width=True)

    # Detail view
    selected = st.selectbox("Inspect trace", filtered["name"].tolist())
    if selected:
        row = manifest[manifest["name"] == selected].iloc[0]
        if row["set"] == "extension":
            tp = cfg.EXT_TRACES_DIR / f"{selected}.txt"
        else:
            tp = cfg.TRACES_DIR / f"{selected}.txt"
        if tp.exists():
            trace = np.array(read_trace(tp))
            stats = trace_stats(trace)

            st.write(f"**{row['description']}**")
            st.write(f"References: {stats['n_refs']:,} | Unique blocks: {stats['n_unique']:,} | "
                     f"Top-10 share: {stats['top10_share']:.1%} | "
                     f"Est. alpha: {stats['estimated_alpha']:.3f}")

            col1, col2 = st.columns(2)
            with col1:
                # Block ID vs time (downsampled)
                step = max(1, len(trace) // 5000)
                fig = px.scatter(x=np.arange(0, len(trace), step),
                                 y=trace[::step],
                                 labels={"x": "Reference index", "y": "Block ID"},
                                 title="Block ID over time (downsampled)")
                fig.update_traces(marker_size=1)
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                # Frequency vs rank (log-log)
                _, counts = np.unique(trace, return_counts=True)
                sorted_counts = np.sort(counts)[::-1]
                ranks = np.arange(1, len(sorted_counts) + 1)
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=np.log10(ranks), y=np.log10(sorted_counts),
                                         mode="markers", marker=dict(size=2),
                                         name="Observed"))
                if not np.isnan(stats["estimated_alpha"]):
                    fit_y = np.log10(sorted_counts[0]) - stats["estimated_alpha"] * np.log10(ranks)
                    fig.add_trace(go.Scatter(x=np.log10(ranks), y=fit_y,
                                             mode="lines", name=f"Fit (alpha={stats['estimated_alpha']:.2f})"))
                fig.update_layout(title="Frequency vs rank (log-log)",
                                  xaxis_title="log10(rank)", yaxis_title="log10(frequency)")
                st.plotly_chart(fig, use_container_width=True)

            # Caption
            if not np.isnan(row.get("alpha", float("nan"))):
                alpha = row["alpha"]
                top10 = stats["top10_share"]
                st.info(f"Alpha {alpha}: {'a few blocks get most traffic' if alpha > 0.8 else 'relatively uniform access'}; "
                        f"the top 10 blocks make up {top10:.0%} of references.")


# ═══════════════════════════════════════════════════════════════════════
# PAGE 3: RUN EXPERIMENTS
# ═══════════════════════════════════════════════════════════════════════

def page_run_experiments():
    st.header("Run experiments")

    if not (cfg.TRACES_DIR / "manifest.csv").exists():
        st.warning("Generate traces first (Step 1).")
        return

    manifest = pd.read_csv(cfg.TRACES_DIR / "manifest.csv")
    policies = list(enabled_policies().keys())

    # Trace selection
    group = st.selectbox("Trace group", ["All", "Zipf only", "Scans", "Loops",
                                          "Extension", "Custom"])
    if group == "Custom":
        selected_traces = st.multiselect("Select traces", manifest["name"].tolist())
    else:
        mapping = {
            "All": manifest["name"].tolist(),
            "Zipf only": manifest[manifest["family"] == "zipf"]["name"].tolist(),
            "Scans": manifest[manifest["family"] == "scan"]["name"].tolist(),
            "Loops": manifest[manifest["family"] == "loop"]["name"].tolist(),
            "Extension": manifest[manifest["set"] == "extension"]["name"].tolist(),
        }
        selected_traces = mapping.get(group, manifest["name"].tolist())

    st.write(f"Selected: {len(selected_traces)} traces, {len(policies)} policies")

    if st.button("Run", key="run_exp"):
        with st.spinner("Running experiments..."):
            from cachesim.engine import run_all_experiments
            cap = cfg.SMALL_CAPACITY if IS_SMALL else cfg.CAPACITY
            sets = cfg.SMALL_SETS if IS_SMALL else cfg.SETS
            ways = cfg.SMALL_WAYS if IS_SMALL else cfg.WAYS
            n = cfg.SMALL_N_REFS if IS_SMALL else cfg.N_REFS
            run_all_experiments(cap, sets, ways, n)
        st.success("Done! Go to Results page.")
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# PAGE 4: RESULTS
# ═══════════════════════════════════════════════════════════════════════

def page_results():
    st.header("Results")

    latest = cfg.RESULTS_DIR / "latest.csv"
    if not latest.exists():
        st.warning("No results yet — run experiments first.")
        return

    df = pd.read_csv(latest)
    manifest_path = cfg.TRACES_DIR / "manifest.csv"
    manifest = pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame()

    if IS_SMALL:
        st.warning("SMALL MODE: not for the report")

    # Separate main runs from sweep
    if "sweep" in df.columns:
        main = df[df["sweep"] == False].copy()
        sweep = df[df["sweep"] == True].copy()
    else:
        main = df.copy()
        sweep = pd.DataFrame()

    tab_names = ["Summary table", "Heatmaps", "Lines", "Loops & scans",
                 "Miss-ratio curves", "Software vs hardware",
                 "Adaptation", "Costs", "Wins", "Export"]
    tabs = st.tabs(tab_names)

    # ── Summary table ──
    with tabs[0]:
        metric = st.selectbox("Metric", ["hit_ratio", "hit_ratio_steady",
                                          "hit_ratio_excl_compulsory"])
        table = charts.summary_table(main, metric)
        st.dataframe(table.style.highlight_max(axis=1, color="#90EE90"),
                      use_container_width=True)
        st.download_button("Download CSV", table.to_csv(), "summary.csv")

        with st.expander("How to read this"):
            st.write("Each cell is the hit ratio (%) for a policy on a trace. "
                     "Green highlights the best policy per trace row. "
                     "Higher is better.")

    # ── Heatmaps ──
    with tabs[1]:
        if not manifest.empty:
            policies = sorted(main["policy"].unique())
            col1, col2 = st.columns(2)
            with col1:
                sel_pol = st.selectbox("Policy", policies, key="hm_pol")
                fig = charts.heatmap_alpha_ws(main, sel_pol, manifest)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                c1, c2 = st.columns(2)
                pol_a = c1.selectbox("Policy A", policies, index=policies.index("LIRS") if "LIRS" in policies else 0, key="diff_a")
                pol_b = c2.selectbox("Policy B", policies, index=policies.index("ARC") if "ARC" in policies else 1, key="diff_b")
                fig = charts.diff_heatmap(main, pol_a, pol_b, manifest)
                st.plotly_chart(fig, use_container_width=True)

    # ── Lines ──
    with tabs[2]:
        if not manifest.empty:
            ws_options = sorted(manifest["ws_multiplier"].dropna().unique())
            for ws in ws_options:
                fig = charts.hr_vs_alpha(main, ws, manifest)
                st.plotly_chart(fig, use_container_width=True)

                with st.expander(f"What stands out (W={ws}C)"):
                    sub = main[main["trace"].str.contains(f"ws{ws}C")]
                    if not sub.empty:
                        best = sub.loc[sub.groupby("trace")["hit_ratio"].idxmax()]
                        best_counts = best["policy"].value_counts()
                        st.write(f"Best policy most often: {best_counts.index[0]} ({best_counts.iloc[0]} traces)")

    # ── Loops and scans ──
    with tabs[3]:
        col1, col2 = st.columns(2)
        with col1:
            fig = charts.loop_bar(main)
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = charts.scan_bar(main)
            st.plotly_chart(fig, use_container_width=True)

        with st.expander("How to read this"):
            st.write("Bars show hit ratio per policy. OPT dashed line is the theoretical ceiling. "
                     "On loops > C, LRU gets 0% while LIRS and BRRIP retain hits.")

    # ── Miss-ratio curves ──
    with tabs[4]:
        if not sweep.empty:
            sweep_traces = sorted(sweep["trace"].unique())
            sel_trace = st.selectbox("Trace", sweep_traces, key="mrc_trace")
            fig = charts.miss_ratio_curve(sweep, sel_trace)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No capacity sweep data available.")

    # ── Software vs hardware ──
    with tabs[5]:
        st.warning("Hardware policies are set-associative and designed for a different regime; "
                   "compare them primarily against SA-LRU, not fully-associative LRU.")
        sw = main[main["policy"].isin(["ARC", "LIRS", "CLOCK-Pro", "CAR", "MQ", "LRU-K", "LRU"])]
        hw = main[main["policy"].isin(["SA-LRU", "SRRIP", "BRRIP", "DRRIP"])]
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Software family")
            if not sw.empty:
                st.dataframe(charts.summary_table(sw).style.highlight_max(axis=1, color="#90EE90"),
                             use_container_width=True)
        with col2:
            st.subheader("Hardware family")
            if not hw.empty:
                st.dataframe(charts.summary_table(hw).style.highlight_max(axis=1, color="#90EE90"),
                             use_container_width=True)

    # ── Adaptation ──
    with tabs[6]:
        st.write("Adaptation metrics are tracked during experiments but not saved to CSV in this version. "
                 "Use the Manual tracing page to see step-by-step p, m_c, or PSEL changes.")

    # ── Costs ──
    with tabs[7]:
        fig = charts.throughput_bar(main)
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("How to read this"):
            st.write("Throughput in references per second. Higher = faster. "
                     "All policies should exceed 100k refs/s except OPT (50k).")

    # ── Wins ──
    with tabs[8]:
        non_opt = main[main["policy"] != "OPT"]
        if not non_opt.empty:
            best = non_opt.loc[non_opt.groupby("trace")["hit_ratio"].idxmax()]
            win_counts = best["policy"].value_counts().reset_index()
            win_counts.columns = ["policy", "wins"]
            st.dataframe(win_counts, use_container_width=True)

            # Average rank
            ranked = non_opt.copy()
            ranked["rank"] = ranked.groupby("trace")["hit_ratio"].rank(ascending=False, method="min")
            avg_rank = ranked.groupby("policy")["rank"].mean().sort_values().reset_index()
            avg_rank.columns = ["policy", "avg_rank"]
            st.dataframe(avg_rank, use_container_width=True)

        with st.expander("What stands out"):
            if not non_opt.empty:
                st.write(f"Most wins: {win_counts.iloc[0]['policy']} with {win_counts.iloc[0]['wins']} traces.")

    # ── Export ──
    with tabs[9]:
        if st.button("Export for report"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                # CSV
                zf.writestr("summary.csv", charts.summary_table(main).to_csv())
                # Manifest
                if manifest_path.exists():
                    zf.write(manifest_path, "manifest.csv")
                # Sizing figure
                sizing_fig = cfg.RESULTS_DIR / "sizing_study.png"
                if sizing_fig.exists():
                    zf.write(sizing_fig, "sizing_study.png")
            st.download_button("Download zip", buf.getvalue(), "report_export.zip")


# ═══════════════════════════════════════════════════════════════════════
# PAGE 5: MANUAL TRACING
# ═══════════════════════════════════════════════════════════════════════

STEP_POLICIES = ["ARC", "LIRS", "CLOCK-Pro", "CAR", "LRU-K", "SRRIP", "LRU", "FIFO"]

BUILTIN_TRACES = {
    "A B C A D B": list("ABCADB"),
    "A B A B A B": list("ABABAB"),
    "A A B C A (reuse-proof)": list("AABCA"),
    "A B C A B D": list("ABCABD"),
    "A B A B S1..S6 A B": list("ABAB") + ["S1","S2","S3","S4","S5","S6"] + list("AB"),
    "A B C D x4 (loop thrash)": list("ABCD") * 4,
}


def page_manual_tracing():
    st.header("Manual tracing — step through algorithms")

    col1, col2, col3 = st.columns(3)
    with col1:
        policy_name = st.selectbox("Policy", STEP_POLICIES)
    with col2:
        trace_choice = st.selectbox("Trace", list(BUILTIN_TRACES.keys()) + ["Custom"])
    with col3:
        cap = st.number_input("Capacity", min_value=1, max_value=100, value=3)

    if trace_choice == "Custom":
        custom = st.text_input("Enter trace (space-separated)", "A B C A D B")
        trace = custom.split()
    else:
        trace = BUILTIN_TRACES[trace_choice]

    # Run the trace and collect states
    from cachesim.policies import get_policy
    cls = get_policy(policy_name)
    if policy_name in ("SRRIP",):
        p = cls(cap, ways=cap, sets=1)
    elif policy_name == "OPT":
        p = cls(cap, trace=trace)
    else:
        p = cls(cap)

    steps = []
    for key in trace:
        hit = p.access(key)
        steps.append({
            "key": key,
            "hit": hit,
            "state": p.state(),
            "explanation": p.explain_last(),
        })

    hm_str = "".join("H" if s["hit"] else "M" for s in steps)

    step_idx = st.slider("Step", 0, len(steps) - 1, 0) if steps else 0

    if steps:
        s = steps[step_idx]
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("Access", s["key"])
            st.metric("Result", "HIT" if s["hit"] else "MISS")
            st.write(f"**Hit/Miss string so far:** `{hm_str[:step_idx+1]}`")
        with col2:
            st.write(f"**Explanation:** {s['explanation']}")
            st.json(s["state"])

    # Full H/M string
    st.write(f"**Full result:** `{hm_str}`")
    st.write(f"**Hits:** {sum(1 for s in steps if s['hit'])} | "
             f"**Misses:** {sum(1 for s in steps if not s['hit'])}")

    # Check my hand trace
    st.markdown("---")
    st.subheader("Check my hand trace")
    my_hm = st.text_input("Enter your H/M string", "")
    if my_hm:
        for i, (expected, mine) in enumerate(zip(hm_str, my_hm.upper())):
            if expected != mine:
                st.error(f"First disagreement at step {i+1} (access {trace[i]}): "
                         f"simulator says {'HIT' if expected == 'H' else 'MISS'}, "
                         f"you said {'HIT' if mine == 'H' else 'MISS'}.")
                st.write(f"Explanation: {steps[i]['explanation']}")
                break
        else:
            if len(my_hm) == len(hm_str):
                st.success("Your hand trace matches the simulator!")
            else:
                st.warning(f"Length mismatch: yours={len(my_hm)}, expected={len(hm_str)}")

    # Export as table
    if steps and st.button("Export as Markdown table"):
        lines = ["| Step | Access | H/M | Explanation |", "|---|---|---|---|"]
        for i, s in enumerate(steps):
            lines.append(f"| {i+1} | {s['key']} | {'H' if s['hit'] else 'M'} | {s['explanation']} |")
        st.code("\n".join(lines), language="markdown")


# ═══════════════════════════════════════════════════════════════════════
# PAGE 6: VERIFICATION
# ═══════════════════════════════════════════════════════════════════════

def page_verification():
    st.header("Verification")
    st.write("Run the pytest suite and see each policy's verification badge.")

    if st.button("Run tests"):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_policies.py", "-v", "--tb=short"],
            capture_output=True, text=True, cwd=str(cfg.PROJECT_ROOT),
        )
        st.code(result.stdout + result.stderr)

    st.markdown("---")
    st.subheader("Verification badges")
    for name in cfg.ENABLED_POLICIES:
        b = badge(name)
        if "hand-verified" in b:
            st.success(f"{name}: {b}")
        else:
            st.warning(f"{name}: {b}")


# ═══════════════════════════════════════════════════════════════════════
# PAGE 7: SIZING & CONFIDENCE
# ═══════════════════════════════════════════════════════════════════════

def page_sizing():
    st.header("Sizing & confidence")

    # Sizing study
    sizing_csv = cfg.RESULTS_DIR / "sizing_study.csv"
    sizing_fig = cfg.RESULTS_DIR / "sizing_study.png"

    if sizing_csv.exists():
        df = pd.read_csv(sizing_csv)
        st.subheader("Sizing study")
        st.write("Shows how hit ratio converges as trace length increases. "
                 "When the line flattens, the trace is long enough.")
        if sizing_fig.exists():
            st.image(str(sizing_fig))

        summary = df.groupby(["trace", "prefix_length", "policy"]).agg(
            mean_hr=("hit_ratio", "mean"),
            std_hr=("hit_ratio", "std"),
        ).reset_index()
        st.dataframe(summary.head(50))
    else:
        st.info("Run the sizing study first (Step 3 on Start page).")

    # Variance study
    var_csv = cfg.RESULTS_DIR / "variance_study.csv"
    if var_csv.exists():
        st.markdown("---")
        st.subheader("Variance study")
        vdf = pd.read_csv(var_csv)
        summary = vdf.groupby(["base_trace", "policy"]).agg(
            mean=("hit_ratio", "mean"),
            std=("hit_ratio", "std"),
        ).reset_index()
        summary["ci95"] = 1.96 * summary["std"]
        summary["mean_pct"] = (summary["mean"] * 100).round(2)
        summary["std_pct"] = (summary["std"] * 100).round(3)
        summary["ci95_pct"] = (summary["ci95"] * 100).round(3)
        st.dataframe(summary[["base_trace", "policy", "mean_pct", "std_pct", "ci95_pct"]],
                     use_container_width=True)

    # Log download
    log_path = cfg.LOGS_DIR / "experiment_log.md"
    if log_path.exists():
        st.markdown("---")
        st.download_button("Download experiment log", log_path.read_text(),
                           "experiment_log.md")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    page = sidebar()
    dispatch = {
        "1. Start here": page_start,
        "2. Datasets": page_datasets,
        "3. Run experiments": page_run_experiments,
        "4. Results": page_results,
        "5. Manual tracing": page_manual_tracing,
        "6. Verification": page_verification,
        "7. Sizing & confidence": page_sizing,
    }
    dispatch[page]()


if __name__ == "__main__":
    main()
else:
    main()
