"""Set-associative hardware cache policies: SA-LRU, SRRIP, BRRIP, DRRIP.

Set index = block_id % num_sets (for integers) or zlib.crc32 based (for others).
RRPV: 2-bit (0..3).
"""
from __future__ import annotations
import zlib
from collections import OrderedDict
from .base import Policy
from . import register

_RRPV_MAX = 3  # 2-bit


def _set_index(key, num_sets: int) -> int:
    if isinstance(key, int):
        return key % num_sets
    return zlib.crc32(str(key).encode()) % num_sets


class _SetAssocBase(Policy):
    """Base for set-associative policies."""

    def __init__(self, capacity: int, *, ways: int = 16, sets: int | None = None,
                 **params) -> None:
        super().__init__(capacity)
        if sets is not None:
            self.num_sets = sets
            self.ways = ways
        else:
            self.ways = ways
            self.num_sets = max(1, capacity // ways)


# ── SA-LRU ──────────────────────────────────────────────────────────────

@register
class SALRU(_SetAssocBase):
    name = "SA-LRU"
    family = "hardware"

    def __init__(self, capacity: int, **params) -> None:
        super().__init__(capacity, **params)
        self._sets: list[OrderedDict] = [OrderedDict() for _ in range(self.num_sets)]

    def access(self, key) -> bool:
        s = _set_index(key, self.num_sets)
        cache_set = self._sets[s]
        if key in cache_set:
            cache_set.move_to_end(key)
            self.hits += 1
            self._last_explanation = f"SA-LRU: hit on {key} in set {s}."
            return True
        if len(cache_set) >= self.ways:
            evicted, _ = cache_set.popitem(last=False)
            self._last_explanation = (
                f"SA-LRU: miss on {key} in set {s}, evicted {evicted}."
            )
        else:
            self._last_explanation = f"SA-LRU: miss on {key} in set {s}, slot available."
        cache_set[key] = True
        self.misses += 1
        return False

    def state(self) -> dict:
        return {f"set_{i}": list(s.keys()) for i, s in enumerate(self._sets) if s}


# ── SRRIP (Hit-Priority) ────────────────────────────────────────────────

class _SRRIPSet:
    """One set for SRRIP-HP."""

    def __init__(self, ways: int) -> None:
        self.ways = ways
        self.entries: dict = {}  # key -> rrpv

    def access(self, key) -> bool:
        if key in self.entries:
            self.entries[key] = 0
            return True
        return False

    def insert(self, key, rrpv: int = 2) -> object | None:
        if len(self.entries) < self.ways:
            self.entries[key] = rrpv
            return None
        victim = self._find_victim()
        del self.entries[victim]
        self.entries[key] = rrpv
        return victim

    def _find_victim(self) -> object:
        while True:
            for k, v in self.entries.items():
                if v == _RRPV_MAX:
                    return k
            # Age all
            for k in self.entries:
                self.entries[k] = min(self.entries[k] + 1, _RRPV_MAX)


@register
class SRRIP(_SetAssocBase):
    name = "SRRIP"
    family = "hardware"

    def __init__(self, capacity: int, **params) -> None:
        super().__init__(capacity, **params)
        self._sets = [_SRRIPSet(self.ways) for _ in range(self.num_sets)]

    def access(self, key) -> bool:
        s = _set_index(key, self.num_sets)
        cache_set = self._sets[s]
        if cache_set.access(key):
            self.hits += 1
            self._last_explanation = f"SRRIP: hit on {key} in set {s}, RRPV set to 0."
            return True
        self.misses += 1
        victim = cache_set.insert(key, rrpv=2)
        if victim is not None:
            self._last_explanation = f"SRRIP: miss on {key} in set {s}, evicted {victim}."
        else:
            self._last_explanation = f"SRRIP: miss on {key} in set {s}, inserted (RRPV=2)."
        return False

    def state(self) -> dict:
        return {f"set_{i}": dict(s.entries) for i, s in enumerate(self._sets) if s.entries}


# ── BRRIP ────────────────────────────────────────────────────────────────

@register
class BRRIP(_SetAssocBase):
    name = "BRRIP"
    family = "hardware"

    def __init__(self, capacity: int, *, epsilon: float = 1 / 32,
                 seed: int = 42, **params) -> None:
        super().__init__(capacity, **params)
        self.epsilon = epsilon
        import numpy as np
        self._rng = np.random.default_rng(seed)
        self._sets = [_SRRIPSet(self.ways) for _ in range(self.num_sets)]
        self._insert_rrpv2_count = 0
        self._insert_total = 0

    def access(self, key) -> bool:
        s = _set_index(key, self.num_sets)
        cache_set = self._sets[s]
        if cache_set.access(key):
            self.hits += 1
            self._last_explanation = f"BRRIP: hit on {key} in set {s}, RRPV set to 0."
            return True
        self.misses += 1
        # Insert at RRPV=3 normally, RRPV=2 with probability epsilon
        self._insert_total += 1
        if self._rng.random() < self.epsilon:
            rrpv = 2
            self._insert_rrpv2_count += 1
        else:
            rrpv = _RRPV_MAX
        victim = cache_set.insert(key, rrpv=rrpv)
        if victim is not None:
            self._last_explanation = (
                f"BRRIP: miss on {key} in set {s}, evicted {victim}, RRPV={rrpv}."
            )
        else:
            self._last_explanation = f"BRRIP: miss on {key} in set {s}, RRPV={rrpv}."
        return False

    def state(self) -> dict:
        return {f"set_{i}": dict(s.entries) for i, s in enumerate(self._sets) if s.entries}


# ── DRRIP ────────────────────────────────────────────────────────────────

@register
class DRRIP(_SetAssocBase):
    name = "DRRIP"
    family = "hardware"

    def __init__(self, capacity: int, *, leader_sets: int = 4,
                 psel_bits: int = 10, epsilon: float = 1 / 32,
                 seed: int = 42, **params) -> None:
        super().__init__(capacity, **params)
        self.leader_sets = leader_sets
        self.psel_max = (1 << psel_bits) - 1
        self.psel = self.psel_max // 2  # start at midpoint
        self.epsilon = epsilon
        import numpy as np
        self._rng = np.random.default_rng(seed)

        self._sets = [_SRRIPSet(self.ways) for _ in range(self.num_sets)]

        # Assign leader sets: first `leader_sets` for SRRIP, next for BRRIP
        # Use deterministic selection spread across the sets
        rng_leader = np.random.default_rng(seed + 1000)
        indices = rng_leader.permutation(self.num_sets)
        self._srrip_leaders = set(indices[:leader_sets].tolist())
        self._brrip_leaders = set(indices[leader_sets:2 * leader_sets].tolist())
        self._followers = set(range(self.num_sets)) - self._srrip_leaders - self._brrip_leaders

        self._psel_history: list[int] = []

    def _insert_policy(self, set_idx: int) -> int:
        """Return the RRPV for insertion based on set type and PSEL."""
        if set_idx in self._srrip_leaders:
            return 2  # SRRIP: always insert at 2
        if set_idx in self._brrip_leaders:
            if self._rng.random() < self.epsilon:
                return 2
            return _RRPV_MAX
        # Follower: use BRRIP if PSEL >= 512, else SRRIP
        if self.psel >= (self.psel_max + 1) // 2:
            if self._rng.random() < self.epsilon:
                return 2
            return _RRPV_MAX
        return 2

    def access(self, key) -> bool:
        s = _set_index(key, self.num_sets)
        cache_set = self._sets[s]
        if cache_set.access(key):
            self.hits += 1
            self._last_explanation = f"DRRIP: hit on {key} in set {s}, RRPV set to 0."
            self._psel_history.append(self.psel)
            return True
        self.misses += 1

        # Update PSEL on misses in leader sets
        if s in self._srrip_leaders:
            self.psel = min(self.psel + 1, self.psel_max)
        elif s in self._brrip_leaders:
            self.psel = max(self.psel - 1, 0)

        rrpv = self._insert_policy(s)
        victim = cache_set.insert(key, rrpv=rrpv)
        if victim is not None:
            self._last_explanation = (
                f"DRRIP: miss on {key} in set {s}, evicted {victim}, RRPV={rrpv}, "
                f"PSEL={self.psel}."
            )
        else:
            self._last_explanation = (
                f"DRRIP: miss on {key} in set {s}, RRPV={rrpv}, PSEL={self.psel}."
            )
        self._psel_history.append(self.psel)
        return False

    def state(self) -> dict:
        return {
            "psel": self.psel,
            "srrip_leaders": sorted(self._srrip_leaders),
            "brrip_leaders": sorted(self._brrip_leaders),
        }
