"""Backend canonical mode set. The SAME list is asserted on the frontend
(web/src/lib/modeParity.test.ts). Changing modes requires updating BOTH, on
purpose — that is the parity guard."""
from __future__ import annotations

from typing import get_args

from src.services.chat.schemas._core import ModeId

CANONICAL_MODES = ["tutor", "qa", "facilitate", "resume"]


def test_modeid_matches_canonical_list():
    assert sorted(get_args(ModeId)) == sorted(CANONICAL_MODES)
