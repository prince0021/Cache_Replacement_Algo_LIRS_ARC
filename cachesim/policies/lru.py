"""LRU (Least Recently Used) — baseline policy."""
from __future__ import annotations
from collections import OrderedDict
from .base import Policy
from . import register


@register
class LRU(Policy):
    name = "LRU"
    family = "baseline"

    def __init__(self, capacity: int, **params) -> None:
        super().__init__(capacity)
        self._cache: OrderedDict = OrderedDict()

    def access(self, key) -> bool:
        if key in self._cache:
            self._cache.move_to_end(key)
            self.hits += 1
            self._last_explanation = f"Hit on {key}: moved to MRU position."
            return True
        if len(self._cache) >= self.capacity:
            evicted, _ = self._cache.popitem(last=False)
            self._last_explanation = (
                f"Miss on {key}: evicted LRU page {evicted}, inserted {key} at MRU."
            )
        else:
            self._last_explanation = f"Miss on {key}: inserted {key} at MRU (cache not full)."
        self._cache[key] = True
        self.misses += 1
        return False

    def state(self) -> dict:
        return {"cache_lru_to_mru": list(self._cache.keys())}
