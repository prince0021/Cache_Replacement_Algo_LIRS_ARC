"""Base class for all cache replacement policies."""
from __future__ import annotations
from typing import Any


class Policy:
    """Common interface that every replacement algorithm implements."""

    name: str = "base"
    family: str = "baseline"  # "software" | "hardware" | "baseline"

    def __init__(self, capacity: int, **params: Any) -> None:
        self.capacity = capacity
        self.hits = 0
        self.misses = 0
        self._last_explanation = ""

    def access(self, key) -> bool:
        """Process one reference.  Return True on hit."""
        raise NotImplementedError

    def state(self) -> dict:
        """Return a JSON-friendly snapshot of internal data structures."""
        return {}

    def explain_last(self) -> str:
        """One plain-English sentence about what the last access did."""
        return self._last_explanation

    # Convenience --------------------------------------------------------
    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_ratio(self) -> float:
        return self.hits / self.total if self.total else 0.0
