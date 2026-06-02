"""Mode-routing guarantees: every ModeId has an explicit v2 runner, and each
mode dispatches to its own agent (no tutor<->qa / resume<->facilitate cross-wiring)."""
from __future__ import annotations

from typing import get_args

import pytest

from src.services.chat.schemas._core import ModeId


def test_every_modeid_has_a_v2_dispatch_entry():
    from src.services.chat.router import _V2_DISPATCH

    declared = set(get_args(ModeId))
    routed = set(_V2_DISPATCH)
    assert declared == routed, (
        f"ModeId/_V2_DISPATCH mismatch — declared-only={declared - routed}, "
        f"routed-only={routed - declared}"
    )
