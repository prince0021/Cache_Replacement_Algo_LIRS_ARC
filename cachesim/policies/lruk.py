"""LRU-K (O'Neil, O'Neil & Weikum, SIGMOD 1993).

Track the last K reference times per block.  Evict the resident block with
the oldest K-th most recent reference (largest backward K-distance).
Uses a heap with lazy deletion for O(log n) per access.
"""
from __future__ import annotations
import heapq
from .base import Policy
from . import register

_INF = float("inf")


@register
class LRUK(Policy):
    name = "LRU-K"
    family = "software"

    def __init__(self, capacity: int, *, k: int = 2, crp: int = 0,
                 history_mult: int = 2, **params) -> None:
        super().__init__(capacity)
        self.k = k
        self.crp = crp
        self.history_size = history_mult * capacity

        self._time = 0
        # key -> list of last K reference times (most recent last)
        self._history: dict[object, list[int]] = {}
        # Resident set
        self._resident: dict[object, bool] = {}
        # Min-heap on (priority, tie_break, key)
        # priority: negative of backward K-distance (we want to evict largest)
        # Actually we use a max-heap by storing (kd, -last_ref, key) and popping max
        # But Python only has min-heap, so we store (-kd, last_ref, key) and pop min
        # Wait: we want to evict the block with the LARGEST backward K-distance.
        # backward K-distance = time - K-th most recent reference (or INF if < K refs)
        # We want a max-heap on backward K-distance. With min-heap, store negative.
        # Actually let's just store the priority directly and use a min-heap where
        # the victim is the one with the smallest (most negative) K-th reference time.
        # Evict the block whose K-th most recent reference time is oldest (smallest).
        # So: min-heap on (kth_ref_time, most_recent_ref_time, key).
        # Blocks with < K refs: kth_ref_time = -INF (evicted first), tie-break by LRU.
        self._heap: list[tuple[float, float, object]] = []
        self._heap_version: dict[object, int] = {}
        self._version = 0

        # History eviction tracking
        self._eviction_order: list[object] = []

    def _priority(self, key: object) -> tuple[float, float]:
        hist = self._history.get(key, [])
        if len(hist) < self.k:
            kth = -_INF
        else:
            kth = hist[-self.k]
        last_ref = hist[-1] if hist else -_INF
        return (kth, last_ref)

    def _push(self, key: object) -> None:
        self._version += 1
        self._heap_version[key] = self._version
        kth, last_ref = self._priority(key)
        heapq.heappush(self._heap, (kth, last_ref, self._version, key))

    def _evict(self) -> object | None:
        while self._heap:
            kth, last_ref, ver, key = heapq.heappop(self._heap)
            if key in self._resident and self._heap_version.get(key) == ver:
                del self._resident[key]
                # Keep history but track for eviction-based cleanup
                self._eviction_order.append(key)
                if len(self._eviction_order) > self.history_size:
                    old = self._eviction_order.pop(0)
                    if old not in self._resident and old in self._history:
                        del self._history[old]
                        self._heap_version.pop(old, None)
                return key
        return None

    def access(self, key) -> bool:
        self._time += 1

        if key in self._resident:
            # Hit
            hist = self._history.setdefault(key, [])
            hist.append(self._time)
            if len(hist) > self.k:
                hist.pop(0)
            self._push(key)
            self.hits += 1
            self._last_explanation = (
                f"LRU-K: hit on {key}, history={hist}."
            )
            return True

        # Miss
        self.misses += 1
        if len(self._resident) >= self.capacity:
            victim = self._evict()
            self._last_explanation = (
                f"LRU-K: miss on {key}, evicted {victim}."
            )
        else:
            self._last_explanation = (
                f"LRU-K: miss on {key}, cache not full."
            )

        # Record history (may have prior history from ghost)
        hist = self._history.setdefault(key, [])
        hist.append(self._time)
        if len(hist) > self.k:
            hist.pop(0)
        self._resident[key] = True
        self._push(key)
        return False

    def state(self) -> dict:
        resident_info = {}
        for k in self._resident:
            resident_info[str(k)] = self._history.get(k, [])
        return {"resident": resident_info, "k": self.k}
