"""CAR — Clock with Adaptive Replacement (Bansal & Modha, FAST 2004).

ARC where T1/T2 are clocks with reference bits and B1/B2 are LRU lists.
Hits only set the reference bit (no move).
"""
from __future__ import annotations
from collections import OrderedDict, deque
from .base import Policy
from . import register


class _ClockEntry:
    __slots__ = ("key", "ref")

    def __init__(self, key, ref: bool = False) -> None:
        self.key = key
        self.ref = ref


@register
class CAR(Policy):
    name = "CAR"
    family = "software"

    def __init__(self, capacity: int, **params) -> None:
        super().__init__(capacity)
        self.p: float = 0.0
        # T1, T2: circular buffers (deque), entries are _ClockEntry
        self.t1: deque[_ClockEntry] = deque()
        self.t2: deque[_ClockEntry] = deque()
        # Fast lookup: key -> _ClockEntry
        self._t1_map: dict = {}
        self._t2_map: dict = {}
        # B1, B2: ghost LRU lists (OrderedDict, LRU at front)
        self.b1: OrderedDict = OrderedDict()
        self.b2: OrderedDict = OrderedDict()
        self._p_history: list[float] = []

    def _replace(self) -> None:
        """Evict one page using the clock mechanism."""
        while True:
            if len(self._t1_map) >= max(1, int(self.p)):
                # Try T1
                if self.t1:
                    entry = self.t1[0]
                    if not entry.ref:
                        self.t1.popleft()
                        del self._t1_map[entry.key]
                        self.b1[entry.key] = True
                        return
                    else:
                        entry.ref = False
                        self.t1.popleft()
                        del self._t1_map[entry.key]
                        new_entry = _ClockEntry(entry.key, ref=False)
                        self.t2.append(new_entry)
                        self._t2_map[entry.key] = new_entry
                else:
                    # T1 empty, must use T2
                    if self.t2:
                        entry = self.t2[0]
                        if not entry.ref:
                            self.t2.popleft()
                            del self._t2_map[entry.key]
                            self.b2[entry.key] = True
                            return
                        else:
                            entry.ref = False
                            self.t2.rotate(-1)
            else:
                # Try T2
                if self.t2:
                    entry = self.t2[0]
                    if not entry.ref:
                        self.t2.popleft()
                        del self._t2_map[entry.key]
                        self.b2[entry.key] = True
                        return
                    else:
                        entry.ref = False
                        self.t2.rotate(-1)
                else:
                    # T2 empty, must use T1
                    if self.t1:
                        entry = self.t1[0]
                        if not entry.ref:
                            self.t1.popleft()
                            del self._t1_map[entry.key]
                            self.b1[entry.key] = True
                            return
                        else:
                            entry.ref = False
                            self.t1.popleft()
                            del self._t1_map[entry.key]
                            new_entry = _ClockEntry(entry.key, ref=False)
                            self.t2.append(new_entry)
                            self._t2_map[entry.key] = new_entry

    def access(self, key) -> bool:
        c = self.capacity

        # Hit in T1
        if key in self._t1_map:
            self._t1_map[key].ref = True
            self.hits += 1
            self._last_explanation = f"CAR: hit on {key} in T1, reference bit set."
            self._p_history.append(self.p)
            return True

        # Hit in T2
        if key in self._t2_map:
            self._t2_map[key].ref = True
            self.hits += 1
            self._last_explanation = f"CAR: hit on {key} in T2, reference bit set."
            self._p_history.append(self.p)
            return True

        self.misses += 1

        # Cache full → replace
        if len(self._t1_map) + len(self._t2_map) == c:
            self._replace()
            if key not in self.b1 and key not in self.b2:
                if len(self._t1_map) + len(self.b1) == c:
                    if self.b1:
                        self.b1.popitem(last=False)
                elif (len(self._t1_map) + len(self._t2_map) +
                      len(self.b1) + len(self.b2) == 2 * c):
                    if self.b2:
                        self.b2.popitem(last=False)

        if key not in self.b1 and key not in self.b2:
            entry = _ClockEntry(key, ref=False)
            self.t1.append(entry)
            self._t1_map[key] = entry
            self._last_explanation = (
                f"CAR: complete miss on {key}, inserted at tail of T1 with ref=0."
            )
        elif key in self.b1:
            d = max(1, len(self.b2) / len(self.b1)) if self.b1 else 1
            self.p = min(self.p + d, float(c))
            del self.b1[key]
            entry = _ClockEntry(key, ref=False)
            self.t2.append(entry)
            self._t2_map[key] = entry
            self._last_explanation = (
                f"CAR: ghost hit in B1 on {key}, p rose to {self.p:.1f}, "
                f"inserted at tail of T2."
            )
        else:
            d = max(1, len(self.b1) / len(self.b2)) if self.b2 else 1
            self.p = max(self.p - d, 0.0)
            del self.b2[key]
            entry = _ClockEntry(key, ref=False)
            self.t2.append(entry)
            self._t2_map[key] = entry
            self._last_explanation = (
                f"CAR: ghost hit in B2 on {key}, p fell to {self.p:.1f}, "
                f"inserted at tail of T2."
            )

        self._p_history.append(self.p)
        return False

    def state(self) -> dict:
        return {
            "T1": [(e.key, e.ref) for e in self.t1],
            "T2": [(e.key, e.ref) for e in self.t2],
            "B1": list(self.b1.keys()),
            "B2": list(self.b2.keys()),
            "p": self.p,
        }
