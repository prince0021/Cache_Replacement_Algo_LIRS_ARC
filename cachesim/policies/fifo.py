"""FIFO (First-In First-Out) — baseline policy."""
from __future__ import annotations
from collections import OrderedDict
from .base import Policy
from . import register


@register
class FIFO(Policy):
    name = "FIFO"
    family = "baseline"

    def __init__(self, capacity: int, **params) -> None:
        super().__init__(capacity)
        self._cache: OrderedDict = OrderedDict()

    def access(self, key) -> bool:
        if key in self._cache:
            self.hits += 1
            self._last_explanation = f"Hit on {key}: no reordering (FIFO keeps insertion order)."
            return True
        if len(self._cache) >= self.capacity:
            evicted, _ = self._cache.popitem(last=False)
            self._last_explanation = (
                f"Miss on {key}: evicted oldest page {evicted}, inserted {key}."
            )
        else:
            self._last_explanation = f"Miss on {key}: inserted {key} (cache not full)."
        self._cache[key] = True
        self.misses += 1
        return False

    def state(self) -> dict:
        return {"cache_oldest_to_newest": list(self._cache.keys())}
