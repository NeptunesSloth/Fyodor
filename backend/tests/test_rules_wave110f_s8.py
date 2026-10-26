"""Wave 110F session 8: promotions on real Oracle text. Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 613.1f, 702.16: "Target creature loses protection from black until end of turn." (Cephalid Snitch): only the black quality goes.
* 704.5g, 120.6: "can't be destroyed by lethal damage unless lethal damage dealt by a single source is marked on it" (Ogre Enforcer).
* 613.1f, 113.6: "Cards in graveyards lose all abilities." (Yixlid Jailer): no flashback from a graveyard; permanents on the battlefield keep theirs.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, protection
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import card_db  # noqa: F401  (fixture DB with EXTRA)
from tests.test_rules_wave100n_multi import answer, ch
from tests.test_rules_wave100n_multi import cast
from tests.wave9c_kit import build, card_named, check, mana, put

EXTRA = [
    real('Yixlid Jailer', '{1}{B}', 2, 'Creature — Zombie Wizard',
         'Cards in graveyards lose all abilities.', ('2', '1'), 'B'),
    real('Cephalid Snitch', '{1}{U}', 2, 'Creature — Octopus Wizard',
         'Sacrifice this creature: Target creature loses protection from black until end of turn.', ('1', '1'), 'U'),
    real('Test Pro-Black 110F', '{1}{W}', 2, 'Creature — Knight', 'Protection from black', ('2', '2'), 'W'),
    real('Test Pro-Black-Red 110F', '{1}{W}', 2, 'Creature — Knight', 'Protection from black and from red', ('2', '2'), 'W'),
    real('Test Black 110F', '{1}{B}', 2, 'Creature — Zombie', '', ('2', '2'), 'B'),
    real('Test Red 110F', '{1}{R}', 2, 'Creature — Goblin', '', ('2', '2'), 'R'),
    real('Ogre Enforcer', '{3}{R}{R}', 5, 'Creature — Ogre',
         "This creature can't be destroyed by lethal damage unless lethal damage dealt by a single source is marked on it.", ('4', '4'), 'R'),
    real('Shock', '{R}', 1, 'Instant', 'Shock deals 2 damage to any target.', None, 'R'),
    real('Lightning Bolt', '{R}', 1, 'Instant', 'Lightning Bolt deals 3 damage to any target.', None, 'R'),
    real('Test Burn 4 110F', '{2}{R}', 3, 'Instant', 'Test Burn 4 110F deals 4 damage to any target.', None, 'R'),
    real('Test Flyer 110F', '{1}{W}', 2, 'Creature — Bird', 'Flying', ('1', '1'), 'W'),
]
_BASE.extend(EXTRA)
NAMES = ["Yixlid Jailer", "Cephalid Snitch", "Ogre Enforcer"]


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("jailer", [False, True])
def test_jailer_blocks_flashback_only_in_graveyards(cards, jailer):
    """613.1f, 702.34a: with the Jailer a graveyard card has no flashback; a flyer on the battlefield keeps flying."""
    s = build(cards, ["Lightning Surge", "Yixlid Jailer", "Test Flyer 110F"], forests=20, islands=20)
    if jailer:
        put(s, "Yixlid Jailer")
    flyer = put(s, "Test Flyer 110F")
    surge = card_named(s, "Lightning Surge")
    act(s, "p1", type="move", card_ids=[surge.id], to={"player": "p1", "zone": "graveyard"})
    assert ("flashback" in ch(s, surge).keywords) != jailer
    assert "flying" in ch(s, flyer).keywords
    mana(s, "p1", R=7)
    if jailer:
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=surge.id, targets=["p2"])
    else:
        act(s, "p1", type="cast_spell", card_id=surge.id, targets=["p2"])
    check(s)


@pytest.mark.parametrize("knight", ["Test Pro-Black 110F", "Test Pro-Black-Red 110F"])
def test_snitch_removes_only_protection_from_black(cards, knight):
    """702.16, 613.1f: black no longer sees protection after the sacrifice; red still does when the knight has it (and the effect ends with the turn)."""
    s = build(cards, ["Cephalid Snitch", knight], ["Test Black 110F", "Test Red 110F"], forests=20, islands=20)
    snitch, pro = put(s, "Cephalid Snitch"), put(s, knight)
    black, red = put(s, "Test Black 110F", pid="p2"), put(s, "Test Red 110F", pid="p2")
    prot = lambda src: protection.protected_from(ch(s, pro), ch(s, src))  # noqa: E731
    assert prot(black) and (prot(red) == (knight == "Test Pro-Black-Red 110F"))
    act(s, "p1", type="activate_ability", card_id=snitch.id, ability=0, targets=[pro.id])
    answer(s)
    assert s.state.cards[snitch.id].zone == "p1:graveyard"
    assert not prot(black) and (prot(red) == (knight == "Test Pro-Black-Red 110F"))
    check(s)


@pytest.mark.parametrize("burn,dies", [(["Shock", "Lightning Bolt"], False), (["Shock", "Test Burn 4 110F"], True), (["Test Burn 4 110F"], True)])
def test_enforcer_dies_only_to_lethal_from_one_source(cards, burn, dies):
    """120.6, 704.5g: 5 damage from two sources is marked but none dealt lethal damage alone: it lives; 4 from one source kills it."""
    s = build(cards, ["Ogre Enforcer", "Shock", "Lightning Bolt", "Test Burn 4 110F"], forests=20, islands=20)
    enforcer = put(s, "Ogre Enforcer")
    for name in burn:
        mana(s, "p1", R=3)
        cast(s, name, [enforcer.id])
        answer(s)
    assert (s.state.cards[enforcer.id].zone == "p1:graveyard") == dies
    assert dies or s.state.cards[enforcer.id].damage >= 4
    check(s)
