"""Central configuration for the cache simulation project.

Every size, seed, path, and parameter list lives here.
"""
from pathlib import Path
import argparse

# ── Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
TRACES_DIR = PROJECT_ROOT / "traces"
EXT_TRACES_DIR = TRACES_DIR / "extension"
RESULTS_DIR = PROJECT_ROOT / "results"
LOGS_DIR = PROJECT_ROOT / "logs"
DOCS_DIR = PROJECT_ROOT / "docs"

# ── Cache geometry ─────────────────────────────────────────────────────
CAPACITY = 2048                         # C blocks (default)
WAYS = 16                               # set-associative ways
SETS = CAPACITY // WAYS                 # 128 sets
DRRIP_LEADER_SETS = 4                   # per component policy
DRRIP_PSEL_BITS = 10                    # 10-bit saturating counter
DRRIP_RRPV_BITS = 2                     # 2-bit RRPV

# ── Small mode (smoke tests) ──────────────────────────────────────────
SMALL_CAPACITY = 256
SMALL_WAYS = 16
SMALL_SETS = SMALL_CAPACITY // SMALL_WAYS  # 16 sets
SMALL_N_REFS = 20_000

# ── Trace generation ──────────────────────────────────────────────────
BASE_SEED = 42
N_REFS = 600_000                        # default trace length

ALPHAS = [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6]
WS_MULTIPLIERS = [0.5, 1.0, 2.0, 10.0]

# One integer block-ID per line, no header, no blank lines.
TRACE_FORMAT = "one_int_per_line"

# ── MQ defaults ────────────────────────────────────────────────────────
MQ_NUM_QUEUES = 8
MQ_LIFE_TIME_MULT = 1       # life_time = MULT * capacity
MQ_QOUT_SIZE_MULT = 1       # qout_size = MULT * capacity

# ── LIRS defaults ──────────────────────────────────────────────────────
LIRS_HIRS_RATIO = 0.01
LIRS_S_BOUND_MULT = 3       # |S| bounded at MULT * C

# ── LRU-K defaults ─────────────────────────────────────────────────────
LRUK_K = 2
LRUK_CRP = 0
LRUK_HISTORY_MULT = 2       # history retained for MULT * C evictions

# ── BRRIP ──────────────────────────────────────────────────────────────
BRRIP_EPSILON = 1 / 32      # probability of inserting at RRPV=2

# ── Enabled policies ──────────────────────────────────────────────────
ENABLED_POLICIES = [
    "LRU",
    "FIFO",
    "OPT",
    "ARC",
    "LIRS",
    "CLOCK-Pro",
    "CAR",
    "MQ",
    "LRU-K",
    "SA-LRU",
    "SRRIP",
    "BRRIP",
    "DRRIP",
]

DROPPED_POLICIES = {
    "SHiP": "Not included: needs PC signatures",
}


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--small", action="store_true",
                        help="Use small mode (C=256, N=20000)")
    parser.add_argument("--refs", type=int, default=None,
                        help="Override trace length N")


def get_capacity(args) -> int:
    return SMALL_CAPACITY if getattr(args, "small", False) else CAPACITY


def get_n_refs(args) -> int:
    if getattr(args, "refs", None):
        return args.refs
    return SMALL_N_REFS if getattr(args, "small", False) else N_REFS


def get_sets(args) -> int:
    return SMALL_SETS if getattr(args, "small", False) else SETS


def get_ways(args) -> int:
    return SMALL_WAYS if getattr(args, "small", False) else WAYS
