"""LIRS — Low Inter-reference Recency Set (Jiang & Zhang, SIGMETRICS 2002).

Blocks are LIR (hot, always resident), resident HIR, or non-resident HIR.
Stack S and queue Q.  Bottom of S is always LIR (maintained by pruning).
"""
from __future__ import annotations
from collections import OrderedDict
from .base import Policy
from . import register


@register
class LIRS(Policy):
    name = "LIRS"
    family = "software"

    def __init__(self, capacity: int, *, hirs_ratio: float = 0.01,
                 s_bound_mult: int = 3, **params) -> None:
        super().__init__(capacity)
        self.l_hirs = max(1, round(hirs_ratio * capacity))
        self.l_lirs = capacity - self.l_hirs
        self.hirs_ratio = hirs_ratio
        self.s_bound = s_bound_mult * capacity

        # Status: 'lir', 'res_hir', 'nonres_hir'
        self._status: dict = {}
        # Stack S: OrderedDict, bottom=popitem(last=False), top=last
        self._s: OrderedDict = OrderedDict()
        # Queue Q: OrderedDict, front=popitem(last=False), end=last
        self._q: OrderedDict = OrderedDict()

        self._n_lir = 0
        self._n_resident = 0  # running counter; never recount
        self._warmup = True

        self._total_pruning_work = 0
        self._max_single_prune = 0

    def _prune_stack(self) -> None:
        """Remove entries from the bottom of S until an LIR block is at the bottom."""
        work = 0
        while self._s:
            bottom_key = next(iter(self._s))
            if self._status.get(bottom_key) == "lir":
                break
            self._s.popitem(last=False)
            work += 1
            if self._status.get(bottom_key) == "nonres_hir":
                del self._status[bottom_key]
        self._total_pruning_work += work
        self._max_single_prune = max(self._max_single_prune, work)

    def _limit_s(self) -> None:
        """Bound |S| by dropping oldest non-resident HIR entries."""
        while len(self._s) > self.s_bound:
            to_remove = None
            for k in self._s:
                if self._status.get(k) == "nonres_hir":
                    to_remove = k
                    break
            if to_remove is None:
                break
            del self._s[to_remove]
            if self._status.get(to_remove) == "nonres_hir":
                del self._status[to_remove]

    def _evict_hir(self) -> object:
        """Evict front of Q. If it's in S, keep it as non-resident HIR."""
        while self._q:
            victim, _ = self._q.popitem(last=False)
            if self._status.get(victim) != "res_hir":
                continue
            if victim in self._s:
                self._status[victim] = "nonres_hir"
            else:
                if victim in self._status:
                    del self._status[victim]
            self._n_resident -= 1
            return victim
        return None

    def access(self, key) -> bool:
        status = self._status.get(key)

        # Warmup: admit as LIR until we have enough
        if self._warmup and status is None:
            if self._n_lir < self.l_lirs:
                self.misses += 1
                self._status[key] = "lir"
                self._s[key] = True
                self._n_lir += 1
                self._n_resident += 1
                if self._n_lir == self.l_lirs:
                    self._warmup = False
                self._last_explanation = (
                    f"LIRS warm-up: miss on {key}, admitted as LIR "
                    f"({self._n_lir}/{self.l_lirs})."
                )
                return False

        # ── Hit on LIR block ──
        if status == "lir":
            self.hits += 1
            was_bottom = (next(iter(self._s)) == key) if self._s else False
            if key in self._s:
                self._s.move_to_end(key)
            else:
                self._s[key] = True
            if was_bottom:
                self._prune_stack()
            self._last_explanation = f"LIRS: hit on LIR block {key}, moved to top of S."
            self._limit_s()
            return True

        # ── Hit on resident HIR block ──
        if status == "res_hir":
            self.hits += 1
            in_s = key in self._s
            if in_s:
                # Promote to LIR
                del self._s[key]
                self._s[key] = True  # top
                self._status[key] = "lir"
                self._n_lir += 1

                # Remove from Q
                if key in self._q:
                    del self._q[key]

                # Demote bottom of S (LIR) to resident HIR
                self._prune_stack()
                if self._s:
                    bottom_key = next(iter(self._s))
                    if self._status.get(bottom_key) == "lir":
                        self._status[bottom_key] = "res_hir"
                        self._n_lir -= 1
                        self._s.popitem(last=False)
                        self._q[bottom_key] = True
                        self._prune_stack()

                self._last_explanation = (
                    f"LIRS: hit on resident HIR {key} in S, promoted to LIR, "
                    f"bottom LIR demoted to HIR."
                )
            else:
                # Not in S: move to top of S and end of Q
                self._s[key] = True
                if key in self._q:
                    del self._q[key]
                self._q[key] = True
                self._last_explanation = (
                    f"LIRS: hit on resident HIR {key} (not in S), "
                    f"moved to top of S and end of Q."
                )
            self._limit_s()
            return True

        # ── Miss ──
        self.misses += 1

        # Evict if full
        if self._n_resident >= self.capacity:
            self._evict_hir()

        if status == "nonres_hir" and key in self._s:
            # Non-resident HIR in S: promote to LIR
            del self._s[key]
            self._s[key] = True  # top
            self._status[key] = "lir"
            self._n_lir += 1
            self._n_resident += 1

            # Demote bottom LIR
            self._prune_stack()
            if self._s:
                bottom_key = next(iter(self._s))
                if self._status.get(bottom_key) == "lir":
                    self._status[bottom_key] = "res_hir"
                    self._n_lir -= 1
                    self._s.popitem(last=False)
                    self._q[bottom_key] = True
                    self._prune_stack()

            self._last_explanation = (
                f"LIRS: miss on non-resident HIR {key} in S, promoted to LIR."
            )
        else:
            # Brand new or non-resident not in S: admit as resident HIR
            self._status[key] = "res_hir"
            self._s[key] = True  # top
            self._q[key] = True  # end
            self._n_resident += 1
            self._last_explanation = (
                f"LIRS: miss on {key}, admitted as resident HIR at top of S and end of Q."
            )

        self._limit_s()
        return False

    def state(self) -> dict:
        s_list = []
        for k in self._s:
            s_list.append((k, self._status.get(k, "?")))
        q_list = list(self._q.keys())
        return {
            "S_bottom_to_top": s_list,
            "Q_front_to_end": q_list,
            "LIR_count": self._n_lir,
            "resident_count": self._n_resident,
            "l_lirs": self.l_lirs,
            "l_hirs": self.l_hirs,
        }
