"""Wave 110C: Toralf, God of Fury // Toralf's Hammer. 120.10: the trigger's amount is the excess noncombat damage; 115.4, 603.3d: "any target other than that permanent"
cannot pick the creature that was dealt the damage. Toralf's Hammer grants the Razor Boomerang kind of ability with a {1}{R} cost and 3 damage (602.2, 701.3b, 120.3)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_attachments import token
from tests.wave9c_kit import build
from tests.wave110c_kit import check, make_db, mana, put, real, to_hand

TORALF = "Trample\nWhenever a creature or planeswalker an opponent controls is dealt excess noncombat damage, Toralf deals damage equal to the excess to any target other than that permanent."
HAMMER = ("Equipped creature has \"{1}{R}, {T}, Unattach Toralf's Hammer: It deals 3 damage to any target. Return Toralf's Hammer to its owner's hand.\"\n"
          "Equipped creature gets +3/+0 as long as it's legendary.\nEquip {1}{R}")
EXTRA = [real("Toralf, God of Fury", "{2}{R}{R}", 4, "Legendary Creature — God", TORALF, ("5", "4"), "R"),
         real("Toralf's Hammer", "", 0, "Artifact — Equipment", HAMMER, None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    # (the real DB card is one DFC: the same two texts)
    assert coverage.of_card_data(cards.resolve("Toralf, God of Fury")).level == "FULL"


def settle_target(s, pick):
    """Pass until the trigger asks for its target: the damaged creature is no option; ``pick`` is chosen."""
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            assert pick in ids
            return ids, d
        if not s.state.rules.stack:
            return None, None
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never settled")


def bolt(s, target):
    c = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[target])


@pytest.mark.parametrize("toughness,excess", [(2, 1), (1, 2), (3, 0)])
def test_trigger_deals_the_excess_to_a_target_other_than_the_creature(cards, toughness, excess):
    s = build(cards, ["Toralf, God of Fury", "Lightning Bolt"])
    put(s, "Toralf, God of Fury")
    victim = token(s, "p2", "Golem", f"2/{toughness}", "Indestructible")  # (indestructible: it stays on the battlefield, so it would be a legal target without the exception)
    bolt(s, victim.id)
    ids, d = settle_target(s, "p2") if excess else (None, None)
    if excess:
        assert victim.id not in ids
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
    for _ in range(10):
        if s.state.rules.stack:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p2"].life == 40 - excess
    check(s)


def test_hammer_gives_the_equipped_creature_a_three_damage_ping(cards):
    from tests.wave110j_kit import activate

    s = build(cards, ["Toralf's Hammer", "Toralf, God of Fury"])
    toralf, hammer = put(s, "Toralf, God of Fury"), put(s, "Toralf's Hammer")
    s.state.rules.controlled_since[toralf.id].turn = 0
    mana(s, C=2, R=1)
    activate(s, hammer, "Equip {1}{R}", targets=[toralf.id])
    assert s.state.cards[hammer.id].attached_to == toralf.id
    mana(s, C=1, R=1)
    activate(s, toralf, "{1}{R}, {T}, Unattach", targets=["p2"])
    assert s.state.players["p2"].life == 37 and s.state.cards[toralf.id].tapped  # (the Hammer, the source, deals 3: 120.3)
    assert s.state.cards[hammer.id].zone == "p1:hand"
    check(s)
