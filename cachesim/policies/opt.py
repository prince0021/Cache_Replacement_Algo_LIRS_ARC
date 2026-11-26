"""OPT (Belady's optimal) — offline baseline with bypass rule.

Two-pass: precompute next-use positions, then use a max-heap on next-use
so each access is O(log C) instead of O(C).
"""
from __future__ import annotations
import heapq
from .base import Policy
from . import register

_INF = float("inf")


@register
class OPT(Policy):
    name = "OPT"
    family = "baseline"

    def __init__(self, capacity: int, *, trace: list | None = None, **params) -> None:
        super().__init__(capacity)
        self._cache: dict[object, int] = {}   # key -> next_use
        # max-heap (negate next_use): (-next_use, key)
        self._heap: list[tuple[int, object]] = []
        self._next_use: list[int] = []
        self._pos = 0
        if trace is not None:
            self._precompute(trace)

    def set_trace(self, trace: list) -> None:
        self._precompute(trace)

    def _precompute(self, trace: list) -> None:
        n = len(trace)
        self._next_use = [0] * n
        last_seen: dict[object, int] = {}
        for i in range(n - 1, -1, -1):
            key = trace[i]
            if key in last_seen:
                self._next_use[i] = last_seen[key]
            else:
                self._next_use[i] = n + 1  # sentinel: never used again
            last_seen[key] = i
        self._pos = 0

    def access(self, key) -> bool:
        pos = self._pos
        next_use = self._next_use[pos] if pos < len(self._next_use) else _INF
        self._pos += 1

        if key in self._cache:
            self._cache[key] = next_use
            heapq.heappush(self._heap, (-next_use, key))
            self.hits += 1
            self._last_explanation = f"Hit on {key}."
            return True

        self.misses += 1

        # Bypass rule: don't admit if incoming block's next use is no
        # sooner than the farthest-future resident block's next use.
        if len(self._cache) >= self.capacity:
            # lazy deletion: pop stale entries
            while self._heap and (self._heap[0][1] not in self._cache or
                                  self._cache[self._heap[0][1]] != -self._heap[0][0]):
                heapq.heappop(self._heap)
            if self._heap:
                victim_next = -self._heap[0][0]
                victim_key = self._heap[0][1]
            else:
                victim_next = -1
                victim_key = None

            if next_use >= victim_next and victim_key is not None:
                self._last_explanation = (
                    f"Miss on {key}: bypassed (next use {next_use} >= victim's {victim_next})."
                )
                return False

            # Evict the farthest-future block
            heapq.heappop(self._heap)
            del self._cache[victim_key]
            self._last_explanation = (
                f"Miss on {key}: evicted {victim_key} (next use {victim_next}), "
                f"inserted {key} (next use {next_use})."
            )
        else:
            self._last_explanation = (
                f"Miss on {key}: inserted {key} (next use {next_use}), cache not full."
            )

        self._cache[key] = next_use
        heapq.heappush(self._heap, (-next_use, key))
        return False

    def state(self) -> dict:
        return {"cache": {str(k): v for k, v in self._cache.items()}}
