"""Wave 110J final pass, real Oracle text. Every scenario ends with replay + save/load.

* Enduring Angel: 614.1a the life-total reduction to 0 or less (damage 120.3a, life loss 119.3) is replaced: it transforms (701.28), life becomes 3
  (119.5); a token or non-double-faced copy cannot, so its controller loses the game (ruling 2015-06-22).
* Aegis of the Legion: 702.134c the equipped creature "mentors" a creature when its mentor ability (granted by the Aegis) resolves with that
  creature as target: the shield counter goes on it; nothing when the target's power is no longer lower at resolution (ruling 2018-07-13).
* Phylactery Lich: 614.12a / 614.1c the artifact is chosen as it enters (no target, ruling 2013-04-15), the counter goes on it; with no artifact
  nothing happens and the state trigger (603.8) sacrifices the Lich; another phylactery counter anywhere keeps it.
"""

from __future__ import annotations

import pytest

from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.wave9c_kit import build, life, mana, to_hand
from tests.wave110j_kit import (  # noqa: F401
    EXTRA,
    ability,
    card_db,
    check,
    full,
    hand_new,
    now,
    put_new,
    settle,
    to_phase,
)

PLAIN = "Plain Angel"  # a single-faced permanent with Enduring Angel's replacement text (what a copy of it is, ruling 2015-06-22)
EXTRA.append(card(PLAIN, set_code="w110j", number="F001", mana_cost="{2}{W}{W}", cmc=4.0, type_line="Creature — Angel", power="3", toughness="3", colors=["W"],
                  color_identity=["W"], keywords=[], layout="normal", oracle_text="If your life total would be reduced to 0 or less, instead transform this creature "
                  "and your life total becomes 3. Then if this creature didn't transform this way, you lose the game."))
LICH, ORNI = "Phylactery Lich", "Ornithopter"
ANGEL, BOLT, BLOOD = "Enduring Angel // Angelic Enforcer", "Lightning Bolt", "Sign in Blood"


@pytest.mark.parametrize("name", [LICH, ANGEL])
def test_full(cards, name):
    from app.rules import coverage

    cov = coverage.of_card_data(cards.resolve(name))
    assert cov.level == "FULL", [f for f in cov.features if not f.supported]


def test_lich_counter_on_chosen_artifact_and_it_stays(cards):
    s = build(cards, [LICH, ORNI], [], forests=30, islands=30)
    orni = put_new(s, ORNI)
    lich = hand_new(s, LICH)
    from tests.wave110j_kit import cost

    mana(s, "p1", **cost(LICH))
    act(s, "p1", type="cast_spell", card_id=lich.id)
    settle(s)
    assert now(s, orni).counters.get("phylactery") == 1
    assert now(s, lich).zone.endswith(":battlefield")
    check(s)


def test_lich_without_an_artifact_is_sacrificed(cards):
    s = build(cards, [LICH], [], forests=30, islands=30)
    lich = hand_new(s, LICH)
    from tests.wave110j_kit import cost

    mana(s, "p1", **cost(LICH))
    act(s, "p1", type="cast_spell", card_id=lich.id)
    settle(s)
    assert now(s, lich).zone.endswith(":graveyard")
    check(s)


def _hit(s, name, target="p1"):
    from tests.wave110j_kit import cast_on

    return cast_on(s, name, target)


@pytest.mark.parametrize("spell", [BOLT, BLOOD])
def test_angel_replaces_a_lethal_reduction(cards, spell):
    """Lightning Bolt (damage) and Sign in Blood (life loss, 3 life lost is not enough: life 2) both reduce p1 to 0 or less."""
    s = build(cards, [ANGEL, BOLT, BLOOD], [], forests=30, islands=30)
    angel = put_new(s, ANGEL)
    act(s, "p1", type="set_life", player="p1", value=2 if spell == BLOOD else 3)
    _hit(s, spell)
    assert life(s, "p1") == 3
    assert now(s, angel).face == 1 and now(s, angel).zone.endswith(":battlefield")
    assert not s.state.rules.lost
    check(s)


def test_angel_does_nothing_for_a_nonlethal_reduction(cards):
    s = build(cards, [ANGEL, BOLT], [], forests=30, islands=30)
    angel = put_new(s, ANGEL)
    _hit(s, BOLT)
    assert life(s, "p1") == 37 and now(s, angel).face == 0
    check(s)


def test_a_single_faced_angel_cannot_transform_so_its_controller_loses(cards):
    s = build(cards, [PLAIN, BOLT], [], forests=30, islands=30)
    angel = put_new(s, PLAIN)
    act(s, "p1", type="set_life", player="p1", value=3)
    _hit(s, BOLT)
    assert now(s, angel).face == 0 and "p1" in s.state.rules.lost
    check(s)


AEGIS, ELVES, BEARS = "Aegis of the Legion", "Llanowar Elves", "Grizzly Bears"


def growth_id(s):
    return next(c.id for c in s.state.cards.values() if c.name == "Giant Growth" and c.zone == "p1:hand")


def _mentor_attack(cards, *, growth=False):
    from tests.wave110j_kit import mana

    s = build(cards, [AEGIS, BEARS, ELVES, "Giant Growth"], [], forests=30, islands=30)
    aegis, bears, elves = put_new(s, AEGIS), put_new(s, BEARS), put_new(s, ELVES)
    to_phase(s, "main1", turn=3)
    mana(s, "p1", **{"C": 3})
    act(s, "p1", type="activate_ability", card_id=aegis.id, ability=ability(s, aegis, "Equip {3}"), targets=[bears.id])
    settle(s)
    assert now(s, aegis).attached_to == bears.id
    if growth:
        to_hand(s, "Giant Growth")
        put_new(s, "Forest")
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}, {"card_id": elves.id, "target": "p2"}])
    return s, bears, elves


def test_aegis_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(AEGIS)).level == "FULL"


def test_aegis_puts_a_shield_counter_on_the_mentored_creature(cards):
    s, bears, elves = _mentor_attack(cards)
    settle(s)  # mentor targets the creature with lesser power (Elves 1 < Bears 3), then the Aegis trigger
    assert now(s, elves).counters.get("+1/+1") == 1 and now(s, elves).counters.get("shield") == 1
    assert not now(s, bears).counters.get("shield")
    check(s)


def test_aegis_gives_no_shield_when_the_target_is_no_longer_lesser_at_resolution(cards):
    """Ruling 2018-07-13: the mentor ability does nothing once the target's power is not lower, so the equipped creature did not mentor it."""
    s, bears, elves = _mentor_attack(cards, growth=True)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[elves.id])  # mentor's target (the only legal one)
    act(s, "p1", type="cast_spell", card_id=growth_id(s), targets=[elves.id])  # in response: Elves 4/4, no longer less than Bears' 3
    settle(s)
    assert not now(s, elves).counters.get("+1/+1") and not now(s, elves).counters.get("shield")
    check(s)
