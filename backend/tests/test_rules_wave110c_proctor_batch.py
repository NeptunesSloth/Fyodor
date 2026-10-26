"""Wave 110C: Strict Proctor and "one or more" enter triggers: one batched trigger (603.2c) is caused by the entering permanents, so each Proctor triggers once
for it (603.2), not once per permanent; the batched ability is countered unless its controller pays {2} (701.6a, 118.12)."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave110c_proctor import PROCTOR, settle_asking
from tests.wave9c_kit import build
from tests.wave110c_kit import cast, check, make_db, mana, put, real

EXTRA = [real("Strict Proctor", "{1}{W}", 2, "Creature — Spirit Cleric", PROCTOR, ("1", "3"), "W"),
         real("Marneus Calgar", "{2}{W}", 3, "Legendary Creature — Astartes", "Master Tactician — Whenever one or more tokens you control enter, draw a card.", ("3", "3"), "W"),
         real("Rune Watcher", "{1}", 1, "Creature — Human", "Whenever one or more permanents you control enter, you gain 1 life.", ("1", "1"), ""),
         real("Panharmonicon", "{4}", 4, "Artifact", "If an artifact or creature entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.", None, ""),
         real("Faith's Reward", "{3}{W}", 4, "Instant", "Return to the battlefield all permanent cards in your graveyard that were put there from the battlefield this turn.", None, "W"),
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


def test_multiplier_extra_added_by_a_later_join_gets_a_proctor(cards):
    """603.2c, 603.2d: Faith's Reward returns a land, then a creature, as one batch of "one or more permanents"; Panharmonicon's extra instance (the creature
    caused it, not the land) is added when the creature joins and still triggers each Proctor (603.2)."""
    s = build(cards, ["Strict Proctor", "Panharmonicon", "Rune Watcher", "Faith's Reward", "Forest", "Grizzly Bears"])
    for n in ("Strict Proctor", "Panharmonicon", "Rune Watcher"):
        put(s, n)
    forest, bears = put(s, "Forest"), put(s, "Grizzly Bears")
    for c in (forest, bears):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, C=3, W=1)
    cast(s, "Faith's Reward")
    pend = s.state.rules.pending_triggers
    assert sorted(p.name for p in pend) == ["Rune Watcher"] * 2 + ["Strict Proctor"] * 2
    check(s)
