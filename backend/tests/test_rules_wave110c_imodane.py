"""Wave 110C: Imodane, the Pyrohammer (603.2, 120.1, 115.9c): damage an instant or sorcery whose only target is a creature deals to that creature."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, cast, check, life, make_db, mana, put, real

TEXT = ("First strike\nWhenever an instant or sorcery spell you control that targets only a single creature deals damage to that creature, "
        "Imodane deals that much damage to each opponent.")
EXTRA = [real("Imodane, the Pyrohammer", "{2}{R}{R}", 4, "Legendary Creature — Human Berserker", TEXT, ("4", "3"), "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Imodane, the Pyrohammer")).level == "FULL"


@pytest.mark.parametrize("target", ["creature", "player"])
def test_only_damage_to_the_single_creature_target_is_copied_to_opponents(cards, target):
    s = build(cards, ["Imodane, the Pyrohammer", "Lightning Bolt"], ["Grizzly Bears"])
    put(s, "Imodane, the Pyrohammer")
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=1)
    cast(s, "Lightning Bolt", [bears.id] if target == "creature" else ["p2"])
    answer(s)
    assert life(s, "p2") == 37  # a creature target: 3 copied to the opponent; the player as the target: 3 once (no copy)
    check(s)
