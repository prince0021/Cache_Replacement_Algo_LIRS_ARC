"""ARC — Adaptive Replacement Cache (Megiddo & Modha, FAST 2003).

Four ordered lists: T1, T2 (resident), B1, B2 (ghost).
Adaptive target p in [0, c].
"""
from __future__ import annotations
from collections import OrderedDict
from .base import Policy
from . import register


@register
class ARC(Policy):
    name = "ARC"
    family = "software"

    def __init__(self, capacity: int, **params) -> None:
        super().__init__(capacity)
        self.p: float = 0.0
        # LRU end = popitem(last=False); MRU end = move_to_end / setitem
        self.t1: OrderedDict = OrderedDict()
        self.t2: OrderedDict = OrderedDict()
        self.b1: OrderedDict = OrderedDict()
        self.b2: OrderedDict = OrderedDict()
        self._p_history: list[float] = []

    def _replace(self, key) -> None:
        """Evict one resident page.  key is still in its ghost list."""
        if self.t1 and (len(self.t1) > self.p or
                        (key in self.b2 and len(self.t1) == int(self.p))):
            old, _ = self.t1.popitem(last=False)
            self.b1[old] = True
        else:
            if self.t2:
                old, _ = self.t2.popitem(last=False)
                self.b2[old] = True
            else:
                old, _ = self.t1.popitem(last=False)
                self.b1[old] = True

    def access(self, key) -> bool:
        c = self.capacity

        # Case I: hit in T1 or T2
        if key in self.t1:
            del self.t1[key]
            self.t2[key] = True
            self.hits += 1
            self._last_explanation = (
                f"ARC Case I: hit on {key} in T1, moved to MRU of T2."
            )
            self._p_history.append(self.p)
            return True

        if key in self.t2:
            self.t2.move_to_end(key)
            self.hits += 1
            self._last_explanation = (
                f"ARC Case I: hit on {key} in T2, moved to MRU of T2."
            )
            self._p_history.append(self.p)
            return True

        self.misses += 1

        # Case II: ghost hit in B1
        if key in self.b1:
            d = 1 if len(self.b1) >= len(self.b2) else len(self.b2) / len(self.b1)
            self.p = min(self.p + d, float(c))
            self._replace(key)
            del self.b1[key]
            self.t2[key] = True
            self._last_explanation = (
                f"ARC Case II: ghost hit in B1 on {key}, p rose to {self.p:.1f}, "
                f"page moved to MRU of T2."
            )
            self._p_history.append(self.p)
            return False

        # Case III: ghost hit in B2
        if key in self.b2:
            d = 1 if len(self.b2) >= len(self.b1) else len(self.b1) / len(self.b2)
            self.p = max(self.p - d, 0.0)
            self._replace(key)
            del self.b2[key]
            self.t2[key] = True
            self._last_explanation = (
                f"ARC Case III: ghost hit in B2 on {key}, p fell to {self.p:.1f}, "
                f"page moved to MRU of T2."
            )
            self._p_history.append(self.p)
            return False

        # Case IV: complete miss
        l1 = len(self.t1) + len(self.b1)
        l2 = len(self.t2) + len(self.b2)

        if l1 == c:
            if len(self.t1) < c:
                self.b1.popitem(last=False)
                self._replace(key)
            else:
                self.t1.popitem(last=False)
        elif l1 < c and (l1 + l2) >= c:
            if (l1 + l2) == 2 * c:
                if self.b2:
                    self.b2.popitem(last=False)
            self._replace(key)

        self.t1[key] = True
        self._last_explanation = (
            f"ARC Case IV: complete miss on {key}, inserted at MRU of T1."
        )
        self._p_history.append(self.p)

        assert len(self.t1) + len(self.t2) <= c, (
            f"Resident overflow: |T1|+|T2|={len(self.t1)+len(self.t2)} > c={c}"
        )
        return False

    def state(self) -> dict:
        return {
            "T1": list(self.t1.keys()),
            "T2": list(self.t2.keys()),
            "B1": list(self.b1.keys()),
            "B2": list(self.b2.keys()),
            "p": self.p,
        }
