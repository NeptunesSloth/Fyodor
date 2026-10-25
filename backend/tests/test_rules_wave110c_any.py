"""Wave 110C: "any opponent may [cost]. If they do, ..." (118.12, 101.4, 603.4).

* Transforming Flourish: the destroyed permanent's controller exiles until a nonland card and may cast it free; they are the caster (608.2g, 118.9).
* Reservoir Kraken: an opponent may tap an untapped creature they control; if one does, the Kraken becomes tapped and its controller gets a Fish (unblockable token).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import to_phase
from tests.wave110c_kit import build, check, make_db, mana, put, real, to_hand

KRAKEN = ("Trample, ward {2}\nAt the beginning of each combat, if this creature is untapped, any opponent may tap an untapped creature they control. If they do, tap this "
          "creature and create a 1/1 blue Fish creature token with \"This token can't be blocked.\"")


FLOURISH = ("Demonstrate (When you cast this spell, you may copy it. If you do, choose an opponent to also copy it. Players may choose new targets for their copies.)\n"
            "Destroy target artifact or creature you don't control. If that permanent is destroyed this way, its controller exiles cards from the top of their library until "
            "they exile a nonland card, then they may cast that card without paying its mana cost.")

EXTRA = [real("Reservoir Kraken", "{3}{U}{U}", 5, "Creature — Kraken", KRAKEN, ("5", "5"), "U"),
         real("Transforming Flourish", "{2}{R}", 3, "Instant", FLOURISH, None, "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Reservoir Kraken", "Transforming Flourish"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _fish(s):
    return [c for c in s.state.cards.values() if c.name == "Fish" and c.zone == "p1:battlefield"]


@pytest.mark.parametrize("pays", [False, True])
def test_reservoir_kraken_opponent_may_tap_a_creature_to_tap_it_and_give_a_fish(cards, pays):
    s = build(cards, ["Reservoir Kraken"], ["Grizzly Bears"])
    kraken, bears = put(s, "Reservoir Kraken"), put(s, "Grizzly Bears", "p2")
    to_phase(s, "begin_combat")
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            pick = ["pay" if pays else "decline"] if "decline" in ids else [bears.id] if bears.id in ids else ids[:1]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[bears.id].tapped == pays and s.state.cards[kraken.id].tapped == pays and len(_fish(s)) == int(pays)
    check(s)


@pytest.mark.parametrize("casts", [False, True])
def test_transforming_flourish_its_controller_may_cast_the_exiled_card_free(cards, casts):
    s = build(cards, ["Transforming Flourish"], ["Grizzly Bears", "Grizzly Bears"])
    ogre = put(s, "Grizzly Bears", "p2")  # the target
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2" and c.id != ogre.id)
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "library"}, position="top")
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Transforming Flourish").id, targets=[ogre.id])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            pick = [bears.id] if casts and bears.id in ids else [i for i in ids if "no" in i.lower() or "decline" in i.lower()] or ids[:0] if d.kind == "choose_cards" else ids[-1:]
            if d.kind == "choose_cards" and not casts:
                pick = []
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[ogre.id].zone == "p2:graveyard"
    assert s.state.cards[bears.id].zone == ("p2:battlefield" if casts else "p2:exile")  # cast by Bob, not Alice
    check(s)
