"""Trace generators, reader/writer, analysis helpers.

IMPORTANT: We do NOT use numpy.random.zipf because:
  1. It raises ValueError for every alpha <= 1.0, and 5 of our 8 alpha
     values are at or below 1.0.
  2. It is unbounded (support is 1..inf), so it cannot control working-set size.

Instead we use a bounded Zipf: ranks 1..n_blocks with probability proportional
to 1/rank^alpha, then shuffle rank->blockID with a seeded permutation.
"""
from __future__ import annotations

import hashlib
import zlib
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

import config as cfg


# ── Seed derivation ────────────────────────────────────────────────────

def _seed_for(name: str) -> int:
    """Deterministic seed from trace name + base seed."""
    h = zlib.crc32(name.encode()) & 0xFFFF_FFFF
    return (cfg.BASE_SEED + h) % (2**31)


# ── Reader / Writer ───────────────────────────────────────────────────

def write_trace(path: Path, trace: Sequence[int]) -> None:
    with open(path, "w") as f:
        for block_id in trace:
            f.write(f"{int(block_id)}\n")


def read_trace(path: Path) -> list[int]:
    with open(path, "r") as f:
        return [int(line) for line in f if line.strip()]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Bounded Zipf generator ────────────────────────────────────────────

def gen_zipf(n_blocks: int, n_refs: int, alpha: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    ranks = np.arange(1, n_blocks + 1, dtype=np.float64)
    p = 1.0 / ranks**alpha
    p /= p.sum()
    draws = rng.choice(n_blocks, size=n_refs, p=p)
    perm = rng.permutation(n_blocks)
    return perm[draws]


# ── Trace generators ──────────────────────────────────────────────────

def gen_zipf_trace(alpha: float, ws_mult: float, capacity: int,
                   n_refs: int, name: str) -> np.ndarray:
    n_blocks = max(1, int(ws_mult * capacity))
    seed = _seed_for(name)
    return gen_zipf(n_blocks, n_refs, alpha, seed)


def gen_scan_pure_long(capacity: int, n_refs: int, name: str) -> np.ndarray:
    """All-unique block IDs."""
    return np.arange(n_refs)


def gen_scan_pure_short(capacity: int, n_refs: int, name: str) -> np.ndarray:
    """10 * C unique blocks, repeated to fill n_refs."""
    n_unique = 10 * capacity
    return np.arange(n_unique)[:n_refs] if n_refs <= n_unique else np.tile(
        np.arange(n_unique), n_refs // n_unique + 1)[:n_refs]


def gen_scanhot(hot_size: int, scan_size: int, capacity: int,
                n_refs: int, name: str) -> np.ndarray:
    """Hot set hit randomly for 5C refs, then a scan of never-seen blocks, repeated."""
    seed = _seed_for(name)
    rng = np.random.default_rng(seed)
    hot_phase_len = 5 * capacity
    result = []
    scan_base = hot_size  # scan blocks start after the hot set
    scan_round = 0
    while len(result) < n_refs:
        # Hot phase
        hot_refs = rng.integers(0, hot_size, size=min(hot_phase_len, n_refs - len(result)))
        result.extend(hot_refs.tolist())
        if len(result) >= n_refs:
            break
        # Scan phase
        scan_start = scan_base + scan_round * scan_size
        scan_len = min(scan_size, n_refs - len(result))
        result.extend(range(scan_start, scan_start + scan_len))
        scan_round += 1
    return np.array(result[:n_refs])


def gen_loop(loop_size: int, n_refs: int) -> np.ndarray:
    """Blocks 0..L-1 repeated."""
    full_reps = n_refs // loop_size
    remainder = n_refs % loop_size
    base = np.arange(loop_size)
    parts = [base] * full_reps
    if remainder:
        parts.append(base[:remainder])
    return np.concatenate(parts)


def gen_filtered(alpha: float, ws_mult: float, l1_mult: float,
                 capacity: int, n_refs: int, name: str) -> np.ndarray:
    """Generate Zipf, pass through LRU of size l1_mult*C, output misses."""
    from cachesim.policies.lru import LRU
    ws = max(1, int(ws_mult * capacity))
    seed = _seed_for(name)
    l1_cap = max(1, int(l1_mult * capacity))
    l1 = LRU(l1_cap)
    rng = np.random.default_rng(seed)

    ranks = np.arange(1, ws + 1, dtype=np.float64)
    p = 1.0 / ranks**alpha
    p /= p.sum()

    misses = []
    batch = 100_000
    while len(misses) < n_refs:
        draws = rng.choice(ws, size=batch, p=p)
        perm_rng = np.random.default_rng(seed + 7777)
        perm = perm_rng.permutation(ws)
        block_ids = perm[draws]
        for bid in block_ids:
            bid = int(bid)
            if not l1.access(bid):
                misses.append(bid)
                if len(misses) >= n_refs:
                    break
    return np.array(misses[:n_refs])


def gen_phase_change(alpha: float, ws_mult: float, phase_len: int,
                     capacity: int, n_refs: int, name: str) -> np.ndarray:
    """Zipf with popularity reshuffled onto new block IDs every phase_len refs."""
    ws = max(1, int(ws_mult * capacity))
    seed = _seed_for(name)
    rng = np.random.default_rng(seed)

    ranks = np.arange(1, ws + 1, dtype=np.float64)
    p = 1.0 / ranks**alpha
    p /= p.sum()

    result = []
    block_offset = 0
    while len(result) < n_refs:
        chunk = min(phase_len, n_refs - len(result))
        draws = rng.choice(ws, size=chunk, p=p)
        perm = rng.permutation(ws)
        block_ids = perm[draws] + block_offset
        result.extend(block_ids.tolist())
        block_offset += ws
    return np.array(result[:n_refs])


def gen_zipf_plus_scan(alpha: float, ws_mult: float, scan_size_mult: float,
                       scan_interval: int, capacity: int, n_refs: int,
                       name: str) -> np.ndarray:
    """Zipf with a scan inserted every scan_interval refs."""
    ws = max(1, int(ws_mult * capacity))
    scan_size = int(scan_size_mult * capacity)
    seed = _seed_for(name)
    rng = np.random.default_rng(seed)

    ranks = np.arange(1, ws + 1, dtype=np.float64)
    p = 1.0 / ranks**alpha
    p /= p.sum()
    perm = rng.permutation(ws)

    result = []
    scan_base = ws
    scan_round = 0
    while len(result) < n_refs:
        # Zipf phase
        chunk = min(scan_interval, n_refs - len(result))
        draws = rng.choice(ws, size=chunk, p=p)
        result.extend(perm[draws].tolist())
        if len(result) >= n_refs:
            break
        # Scan phase
        scan_start = scan_base + scan_round * scan_size
        scan_len = min(scan_size, n_refs - len(result))
        result.extend(range(scan_start, scan_start + scan_len))
        scan_round += 1
    return np.array(result[:n_refs])


# ── Analysis helpers ──────────────────────────────────────────────────

def trace_stats(trace: np.ndarray | list) -> dict:
    arr = np.asarray(trace)
    n = len(arr)
    if n == 0:
        return {"n_refs": 0, "n_unique": 0}
    unique, counts = np.unique(arr, return_counts=True)
    n_unique = len(unique)
    sorted_counts = np.sort(counts)[::-1]
    top10_share = sorted_counts[:10].sum() / n if n > 0 else 0.0

    # Estimated alpha: neg slope of log(freq) vs log(rank) over top half
    n_top = max(2, n_unique // 2)
    freqs = sorted_counts[:n_top].astype(float)
    ranks_fit = np.arange(1, n_top + 1, dtype=float)
    if n_top >= 2 and freqs[-1] > 0:
        log_r = np.log(ranks_fit)
        log_f = np.log(freqs)
        slope, _ = np.polyfit(log_r, log_f, 1)
        est_alpha = -slope
    else:
        est_alpha = float("nan")

    # Reuse distance (sample up to 20k refs)
    sample_size = min(20_000, n)
    sample = arr[:sample_size]
    rd = _reuse_distances(sample)

    return {
        "n_refs": n,
        "n_unique": n_unique,
        "top10_share": round(top10_share, 4),
        "estimated_alpha": round(est_alpha, 3),
        "reuse_dist_median": float(np.median(rd)) if len(rd) > 0 else float("nan"),
        "reuse_dist_p90": float(np.percentile(rd, 90)) if len(rd) > 0 else float("nan"),
    }


def _reuse_distances(trace: np.ndarray) -> np.ndarray:
    """Compute reuse distances for each reference that has a previous occurrence."""
    last_seen: dict[int, int] = {}
    distances = []
    for i, key in enumerate(trace):
        key = int(key)
        if key in last_seen:
            distances.append(i - last_seen[key])
        last_seen[key] = i
    return np.array(distances) if distances else np.array([], dtype=int)


# ── Generate all traces ───────────────────────────────────────────────

def generate_all(capacity: int, n_refs: int, traces_dir: Path,
                 ext_dir: Path, verbose: bool = True) -> pd.DataFrame:
    """Generate all 48 traces and return the manifest DataFrame."""
    traces_dir.mkdir(parents=True, exist_ok=True)
    ext_dir.mkdir(parents=True, exist_ok=True)

    records = []

    # ── 32 Zipfian traces ──
    for alpha in cfg.ALPHAS:
        for ws_mult in cfg.WS_MULTIPLIERS:
            ws_blocks = max(1, int(ws_mult * capacity))
            name = f"zipf_a{alpha}_ws{ws_mult}C"
            if verbose:
                print(f"  Generating {name}...")
            trace = gen_zipf_trace(alpha, ws_mult, capacity, n_refs, name)
            path = traces_dir / f"{name}.txt"
            write_trace(path, trace)
            stats = trace_stats(trace)
            records.append({
                "name": name, "set": "core", "family": "zipf",
                "alpha": alpha, "ws_multiplier": ws_mult,
                "ws_blocks": ws_blocks, "n_refs": n_refs,
                "n_unique": stats["n_unique"],
                "seed": _seed_for(name),
                "estimated_alpha": stats["estimated_alpha"],
                "sha256": sha256_file(path),
                "description": f"Zipf alpha={alpha}, W={ws_mult}C ({ws_blocks} blocks)",
            })

    # ── 4 scan traces ──
    # scan_pure_long
    name = "scan_pure_long"
    if verbose:
        print(f"  Generating {name}...")
    trace = gen_scan_pure_long(capacity, n_refs, name)
    path = traces_dir / f"{name}.txt"
    write_trace(path, trace)
    stats = trace_stats(trace)
    records.append({
        "name": name, "set": "core", "family": "scan",
        "alpha": float("nan"), "ws_multiplier": float("nan"),
        "ws_blocks": n_refs, "n_refs": n_refs,
        "n_unique": stats["n_unique"], "seed": _seed_for(name),
        "estimated_alpha": stats["estimated_alpha"],
        "sha256": sha256_file(path),
        "description": "Pure scan: all-unique IDs, 0% hit for every policy",
    })

    # scan_pure_short
    name = "scan_pure_short"
    if verbose:
        print(f"  Generating {name}...")
    trace = gen_scan_pure_short(capacity, n_refs, name)
    path = traces_dir / f"{name}.txt"
    write_trace(path, trace)
    stats = trace_stats(trace)
    records.append({
        "name": name, "set": "core", "family": "scan",
        "alpha": float("nan"), "ws_multiplier": 10.0,
        "ws_blocks": 10 * capacity, "n_refs": n_refs,
        "n_unique": stats["n_unique"], "seed": _seed_for(name),
        "estimated_alpha": stats["estimated_alpha"],
        "sha256": sha256_file(path),
        "description": "Pure scan: 10*C unique blocks, 0% hit for every policy",
    })

    # scanhot traces
    for scan_mult in [3, 10]:
        hot_size = capacity // 2
        scan_size = scan_mult * capacity
        name = f"scanhot_h0.5C_s{scan_mult}C"
        if verbose:
            print(f"  Generating {name}...")
        trace = gen_scanhot(hot_size, scan_size, capacity, n_refs, name)
        path = traces_dir / f"{name}.txt"
        write_trace(path, trace)
        stats = trace_stats(trace)
        records.append({
            "name": name, "set": "core", "family": "scan",
            "alpha": float("nan"), "ws_multiplier": float("nan"),
            "ws_blocks": hot_size, "n_refs": n_refs,
            "n_unique": stats["n_unique"], "seed": _seed_for(name),
            "estimated_alpha": stats["estimated_alpha"],
            "sha256": sha256_file(path),
            "description": (f"Hot set of 0.5C blocks + scan of {scan_mult}C blocks; "
                            f"tests scan resistance"),
        })

    # ── 4 loop traces ──
    for loop_mult in [0.90, 1.00, 1.10, 1.25]:
        loop_size = max(1, int(loop_mult * capacity))
        name = f"loop_{loop_mult:.2f}C"
        if verbose:
            print(f"  Generating {name}...")
        trace = gen_loop(loop_size, n_refs)
        path = traces_dir / f"{name}.txt"
        write_trace(path, trace)
        stats = trace_stats(trace)
        records.append({
            "name": name, "set": "core", "family": "loop",
            "alpha": float("nan"), "ws_multiplier": loop_mult,
            "ws_blocks": loop_size, "n_refs": n_refs,
            "n_unique": stats["n_unique"], "seed": _seed_for(name),
            "estimated_alpha": stats["estimated_alpha"],
            "sha256": sha256_file(path),
            "description": f"Loop of {loop_size} blocks ({loop_mult}C)",
        })

    # ═══ Extension set: 8 traces ═══

    # 4 filtered traces
    for alpha in [0.8, 1.0]:
        for l1_mult in [0.5, 1.0]:
            name = f"ext_filtered_a{alpha}_L1x{l1_mult}C"
            if verbose:
                print(f"  Generating {name}...")
            trace = gen_filtered(alpha, 20.0, l1_mult, capacity, n_refs, name)
            path = ext_dir / f"{name}.txt"
            write_trace(path, trace)
            stats = trace_stats(trace)
            records.append({
                "name": name, "set": "extension", "family": "filtered",
                "alpha": alpha, "ws_multiplier": 20.0,
                "ws_blocks": 20 * capacity, "n_refs": n_refs,
                "n_unique": stats["n_unique"], "seed": _seed_for(name),
                "estimated_alpha": stats["estimated_alpha"],
                "sha256": sha256_file(path),
                "description": (f"Filtered Zipf a={alpha} W=20C through LRU "
                                f"L1={l1_mult}C; weak temporal locality"),
            })

    # 2 phase-change traces
    for phase_len in [20_000, 100_000]:
        name = f"ext_phasechange_a0.9_P{phase_len}"
        if verbose:
            print(f"  Generating {name}...")
        trace = gen_phase_change(0.9, 4.0, phase_len, capacity, n_refs, name)
        path = ext_dir / f"{name}.txt"
        write_trace(path, trace)
        stats = trace_stats(trace)
        records.append({
            "name": name, "set": "extension", "family": "phase_change",
            "alpha": 0.9, "ws_multiplier": 4.0,
            "ws_blocks": 4 * capacity, "n_refs": n_refs,
            "n_unique": stats["n_unique"], "seed": _seed_for(name),
            "estimated_alpha": stats["estimated_alpha"],
            "sha256": sha256_file(path),
            "description": (f"Phase-change Zipf a=0.9, W=4C, reshuffle every "
                            f"{phase_len} refs; tests adaptation"),
        })

    # 2 zipf-plus-scan traces
    for scan_mult in [3, 10]:
        name = f"ext_zipfscan_a1.0_s{scan_mult}C"
        if verbose:
            print(f"  Generating {name}...")
        trace = gen_zipf_plus_scan(1.0, 2.0, float(scan_mult), 20_000,
                                   capacity, n_refs, name)
        path = ext_dir / f"{name}.txt"
        write_trace(path, trace)
        stats = trace_stats(trace)
        records.append({
            "name": name, "set": "extension", "family": "zipf_scan",
            "alpha": 1.0, "ws_multiplier": 2.0,
            "ws_blocks": 2 * capacity, "n_refs": n_refs,
            "n_unique": stats["n_unique"], "seed": _seed_for(name),
            "estimated_alpha": stats["estimated_alpha"],
            "sha256": sha256_file(path),
            "description": (f"Zipf a=1.0 W=2C with {scan_mult}C scan every 20k refs"),
        })

    manifest = pd.DataFrame(records)
    manifest.to_csv(traces_dir / "manifest.csv", index=False)
    if verbose:
        print(f"\n  Manifest written: {len(manifest)} traces")
    return manifest
