"""CLOCK-Pro (Jiang, Chen & Zhang, USENIX ATC 2005).

One circular list with hot, resident cold, non-resident cold pages.
Three hands: hand_hot, hand_cold, hand_test.
Adaptive cold-page target m_c.
"""
from __future__ import annotations
from .base import Policy
from . import register


class _Page:
    __slots__ = ("key", "hot", "resident", "ref", "test", "prev", "next")

    def __init__(self, key, hot: bool = False, resident: bool = True) -> None:
        self.key = key
        self.hot = hot
        self.resident = resident
        self.ref = False
        self.test = False
        self.prev: _Page | None = None
        self.next: _Page | None = None


@register
class CLOCKPro(Policy):
    name = "CLOCK-Pro"
    family = "software"

    def __init__(self, capacity: int, **params) -> None:
        super().__init__(capacity)
        self._pages: dict[object, _Page] = {}
        self._n_hot = 0
        self._n_cold_resident = 0
        self._n_cold_nonresident = 0
        self._m_c = capacity  # target number of cold resident pages
        self._m_c_history: list[int] = []

        # Sentinel node for the circular list
        self._sentinel = _Page(None, hot=False, resident=False)
        self._sentinel.prev = self._sentinel
        self._sentinel.next = self._sentinel

        self._hand_hot = self._sentinel
        self._hand_cold = self._sentinel
        self._hand_test = self._sentinel

    @property
    def _n_resident(self) -> int:
        return self._n_hot + self._n_cold_resident

    def _insert_before(self, node: _Page, ref_node: _Page) -> None:
        node.prev = ref_node.prev
        node.next = ref_node
        ref_node.prev.next = node
        ref_node.prev = node

    def _remove(self, node: _Page) -> None:
        if self._hand_hot is node:
            self._hand_hot = node.prev
            if self._hand_hot is self._sentinel:
                self._hand_hot = self._sentinel.prev
        if self._hand_cold is node:
            self._hand_cold = node.prev
            if self._hand_cold is self._sentinel:
                self._hand_cold = self._sentinel.prev
        if self._hand_test is node:
            self._hand_test = node.prev
            if self._hand_test is self._sentinel:
                self._hand_test = self._sentinel.prev
        node.prev.next = node.next
        node.next.prev = node.prev
        node.prev = None
        node.next = None

    def _run_hand_cold(self) -> None:
        """Advance hand_cold to find a cold resident page to evict."""
        limit = 2 * (self._n_hot + self._n_cold_resident + self._n_cold_nonresident + 1)
        for _ in range(limit):
            h = self._hand_cold
            if h is self._sentinel:
                self._hand_cold = self._sentinel.next
                if self._hand_cold is self._sentinel:
                    return
                continue
            # Advance first
            self._hand_cold = h.next if h.next is not self._sentinel else self._sentinel.next

            if h.hot or not h.resident:
                continue

            if h.ref:
                # Cold page referenced during test → promote to hot
                h.ref = False
                h.hot = True
                self._n_cold_resident -= 1
                self._n_hot += 1
                self._m_c = max(1, self._m_c - 1)
                self._run_hand_hot_trim()
                continue

            # Found unreferenced cold resident page → evict
            h.resident = False
            self._n_cold_resident -= 1
            if h.test:
                # Keep as non-resident for test period
                self._n_cold_nonresident += 1
            else:
                self._remove(h)
                del self._pages[h.key]
            return

    def _run_hand_hot_trim(self) -> None:
        """Demote hot pages if we have too many (n_hot > capacity - m_c)."""
        target = max(1, self.capacity - self._m_c)
        limit = 2 * (self._n_hot + self._n_cold_resident + self._n_cold_nonresident + 1)
        iters = 0
        while self._n_hot > target and iters < limit:
            iters += 1
            h = self._hand_hot
            if h is self._sentinel:
                self._hand_hot = self._sentinel.next
                if self._hand_hot is self._sentinel:
                    return
                continue
            self._hand_hot = h.prev if h.prev is not self._sentinel else self._sentinel.prev

            if not h.hot:
                continue

            if h.ref:
                h.ref = False
                continue

            # Demote to cold resident
            h.hot = False
            h.resident = True
            h.test = False
            self._n_hot -= 1
            self._n_cold_resident += 1
            return

    def _expire_nonresident(self) -> None:
        """Remove excess non-resident cold pages via hand_test."""
        limit = 2 * (self._n_hot + self._n_cold_resident + self._n_cold_nonresident + 1)
        iters = 0
        while self._n_cold_nonresident > self.capacity and iters < limit:
            iters += 1
            h = self._hand_test
            if h is self._sentinel:
                self._hand_test = self._sentinel.next
                if self._hand_test is self._sentinel:
                    return
                continue
            self._hand_test = h.prev if h.prev is not self._sentinel else self._sentinel.prev

            if h.hot or h.resident:
                continue

            # Non-resident cold with test expired
            if h.test:
                self._m_c = min(self._m_c + 1, self.capacity)
            self._n_cold_nonresident -= 1
            self._remove(h)
            del self._pages[h.key]

    def access(self, key) -> bool:
        page = self._pages.get(key)

        if page is not None and page.resident:
            # Hit
            self.hits += 1
            page.ref = True
            if page.hot:
                self._last_explanation = (
                    f"CLOCK-Pro: hit on hot page {key}, reference bit set."
                )
            else:
                self._last_explanation = (
                    f"CLOCK-Pro: hit on cold resident page {key}, reference bit set."
                )
            self._m_c_history.append(self._m_c)
            return True

        self.misses += 1

        # Need space?
        if self._n_resident >= self.capacity:
            self._run_hand_cold()

        if page is not None and not page.resident:
            # Non-resident page re-referenced → promote to hot
            page.resident = True
            page.hot = True
            page.ref = False
            page.test = False
            self._n_cold_nonresident -= 1
            self._n_hot += 1
            self._m_c = min(self._m_c + 1, self.capacity)
            # Move to "front" (before hand_hot)
            self._remove(page)
            self._insert_before(page, self._hand_hot if self._hand_hot is not self._sentinel
                                else self._sentinel)
            self._run_hand_hot_trim()
            self._last_explanation = (
                f"CLOCK-Pro: miss on non-resident {key}, promoted to hot, m_c={self._m_c}."
            )
        else:
            # Brand new page → cold resident with test period
            page = _Page(key, hot=False, resident=True)
            page.ref = False
            page.test = True
            self._pages[key] = page
            self._n_cold_resident += 1
            self._insert_before(page, self._hand_hot if self._hand_hot is not self._sentinel
                                else self._sentinel)
            if self._hand_cold is self._sentinel:
                self._hand_cold = page
            if self._hand_test is self._sentinel:
                self._hand_test = page
            if self._hand_hot is self._sentinel:
                self._hand_hot = page
            self._last_explanation = (
                f"CLOCK-Pro: miss on new page {key}, inserted as cold resident (test period), "
                f"m_c={self._m_c}."
            )

        self._expire_nonresident()
        self._m_c_history.append(self._m_c)
        return False

    def state(self) -> dict:
        pages = []
        node = self._sentinel.next
        while node is not self._sentinel:
            pages.append({
                "key": node.key,
                "hot": node.hot,
                "resident": node.resident,
                "ref": node.ref,
                "test": node.test,
            })
            node = node.next
        return {
            "clock_list": pages,
            "n_hot": self._n_hot,
            "n_cold_resident": self._n_cold_resident,
            "n_cold_nonresident": self._n_cold_nonresident,
            "m_c": self._m_c,
        }
