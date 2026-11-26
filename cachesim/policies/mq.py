"""MQ — Multi-Queue (Zhou, Philbin & Li, USENIX ATC 2001).

m LRU queues Q0..Q(m-1), a ghost FIFO Qout, per-block access count and
expiry.  Queue number = min(floor(log2(f)), m-1).
"""
from __future__ import annotations
import math
from collections import OrderedDict, deque
from .base import Policy
from . import register


@register
class MQ(Policy):
    name = "MQ"
    family = "software"

    def __init__(self, capacity: int, *, m: int = 8,
                 life_time: int | None = None,
                 qout_size: int | None = None, **params) -> None:
        super().__init__(capacity)
        self.m = m
        self.life_time = life_time if life_time is not None else capacity
        self.qout_size = qout_size if qout_size is not None else capacity

        # Q0..Q(m-1): OrderedDict (LRU at front, MRU at end)
        self._queues: list[OrderedDict] = [OrderedDict() for _ in range(m)]
        # key -> (queue_index, access_count, expire_time)
        self._meta: dict = {}
        self._n_resident = 0

        # Ghost FIFO: deque of (key, access_count)
        self._qout: deque = deque()
        self._qout_set: dict = {}  # key -> access_count

        self._time = 0

    def _queue_num(self, f: int) -> int:
        if f <= 0:
            return 0
        return min(int(math.log2(f)), self.m - 1)

    def _adjust(self) -> None:
        """Demote blocks whose expireTime < current time."""
        for k in range(self.m - 1, 0, -1):
            q = self._queues[k]
            while q:
                lru_key = next(iter(q))
                qi, fc, exp = self._meta[lru_key]
                if exp < self._time:
                    del q[lru_key]
                    new_q = k - 1
                    new_exp = self._time + self.life_time
                    self._queues[new_q][lru_key] = True
                    self._meta[lru_key] = (new_q, fc, new_exp)
                else:
                    break

    def _evict(self) -> None:
        """Evict the LRU block of the lowest non-empty queue."""
        for k in range(self.m):
            q = self._queues[k]
            if q:
                victim, _ = q.popitem(last=False)
                _, fc, _ = self._meta[victim]
                del self._meta[victim]
                self._n_resident -= 1
                # Record in Qout
                if len(self._qout) >= self.qout_size:
                    old_key = self._qout.popleft()
                    if old_key in self._qout_set:
                        del self._qout_set[old_key]
                self._qout.append(victim)
                self._qout_set[victim] = fc
                return

    def access(self, key) -> bool:
        self._time += 1
        self._adjust()

        if key in self._meta:
            # Hit
            qi, fc, _ = self._meta[key]
            del self._queues[qi][key]
            fc += 1
            new_q = self._queue_num(fc)
            new_exp = self._time + self.life_time
            self._queues[new_q][key] = True
            self._meta[key] = (new_q, fc, new_exp)
            self.hits += 1
            self._last_explanation = (
                f"MQ: hit on {key}, f={fc}, moved from Q{qi} to Q{new_q}."
            )
            return True

        # Miss
        self.misses += 1
        if self._n_resident >= self.capacity:
            self._evict()

        # Check Qout
        fc = 0
        if key in self._qout_set:
            fc = self._qout_set[key]
            del self._qout_set[key]
            # Remove from deque (mark as gone; will be skipped on eviction)
            # We can't efficiently remove from middle of deque, so just remove from set.
            # The deque entry becomes a no-op when it reaches the front.

        fc += 1
        new_q = self._queue_num(fc)
        new_exp = self._time + self.life_time
        self._queues[new_q][key] = True
        self._meta[key] = (new_q, fc, new_exp)
        self._n_resident += 1

        if fc > 1:
            self._last_explanation = (
                f"MQ: miss on {key}, found in Qout with f={fc-1}, "
                f"inserted into Q{new_q} with f={fc}."
            )
        else:
            self._last_explanation = (
                f"MQ: miss on {key}, new block, inserted into Q{new_q} with f={fc}."
            )
        return False

    def state(self) -> dict:
        queues = {}
        for i in range(self.m):
            if self._queues[i]:
                queues[f"Q{i}"] = list(self._queues[i].keys())
        return {
            "queues": queues,
            "qout_size": len(self._qout_set),
            "time": self._time,
        }
