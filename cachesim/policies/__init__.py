"""Policy registry — adding a policy means adding one file and one import here."""
from __future__ import annotations
from typing import Dict, Type
from .base import Policy

REGISTRY: Dict[str, Type[Policy]] = {}

_HAND_VERIFIED: Dict[str, int] = {}


def register(cls: Type[Policy]) -> Type[Policy]:
    """Decorator: register a policy class by its .name attribute."""
    REGISTRY[cls.name] = cls
    return cls


def set_hand_verified(name: str, count: int) -> None:
    _HAND_VERIFIED[name] = count


def badge(name: str) -> str:
    n = _HAND_VERIFIED.get(name, 0)
    if n >= 3:
        return f"hand-verified ({n} tests)"
    return "tests derived from paper description, review recommended"


def get_policy(name: str) -> Type[Policy]:
    return REGISTRY[name]


def enabled_policies():
    from config import ENABLED_POLICIES
    return {k: v for k, v in REGISTRY.items() if k in ENABLED_POLICIES}


# Import every policy module so they self-register on import.
from . import lru, fifo, opt, arc, lirs, clockpro, car, mq, lruk, setassoc  # noqa: E402,F401

# Hand-derived test counts (from tests/test_policies.py)
set_hand_verified("LRU", 7)
set_hand_verified("FIFO", 4)
set_hand_verified("OPT", 3)
set_hand_verified("ARC", 9)
set_hand_verified("LIRS", 8)
set_hand_verified("CLOCK-Pro", 4)
set_hand_verified("CAR", 4)
set_hand_verified("MQ", 4)
set_hand_verified("LRU-K", 4)
set_hand_verified("SA-LRU", 3)
set_hand_verified("SRRIP", 4)
set_hand_verified("BRRIP", 3)
set_hand_verified("DRRIP", 3)
