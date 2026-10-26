"""Wave 110C: Strict Proctor and "one or more" enter triggers: one batched trigger (603.2c) is caused by the entering permanents, so each Proctor triggers once
for it (603.2), not once per permanent; the batched ability is countered unless its controller pays {2} (701.6a, 118.12)."""

from __future__ import annotations

import pytest

from tests.test_rules_wave110c_proctor import PROCTOR, settle_asking
from tests.wave9c_kit import build
from tests.wave110c_kit import cast, check, make_db, mana, put, real

EXTRA = [real("Strict Proctor", "{1}{W}", 2, "Creature — Spirit Cleric", PROCTOR, ("1", "3"), "W"),
         real("Marneus Calgar", "{2}{W}", 3, "Legendary Creature — Astartes", "Master Tactician — Whenever one or more tokens you control enter, draw a card.", ("3", "3"), "W"),
         real("Twin Maker", "{1}", 1, "Sorcery", "Create two 1/1 white Soldier creature tokens.", None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def hand(s):
    return len(s.state.zones["p1:hand"])


@pytest.mark.parametrize("pay,drawn", [("decline", 0), ("pay", 1)])
def test_two_tokens_one_batched_trigger_one_proctor(cards, pay, drawn):
    s = build(cards, ["Strict Proctor", "Marneus Calgar", "Twin Maker"])
    put(s, "Strict Proctor")
    put(s, "Marneus Calgar")
    mana(s, C=3)
    cast(s, "Twin Maker")
    settle_asking(s, ["Marneus Calgar", "Strict Proctor"], pay)
    assert hand(s) == drawn  # (the draw happens only if paid)
    check(s)
