"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core import profiles
from app.core import trade as trade_module


@pytest.fixture
def clean_profile_registry() -> Iterator[None]:
    """Snapshot the load-profile registry and restore it afterwards.

    Tests that register a profile would otherwise leak it into later tests and make the
    suite order-dependent. Confining the reach into the registry's internals to this one
    fixture keeps the production API free of a test-only unregister hook.
    """
    original = dict(profiles._REGISTRY)
    yield
    profiles._REGISTRY.clear()
    profiles._REGISTRY.update(original)


@pytest.fixture
def clean_trade_type_registry() -> Iterator[None]:
    """Snapshot the trade-type registry and restore it afterwards."""
    original = dict(trade_module._TRADE_TYPES)
    yield
    trade_module._TRADE_TYPES.clear()
    trade_module._TRADE_TYPES.update(original)
