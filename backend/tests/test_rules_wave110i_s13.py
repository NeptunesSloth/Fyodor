"""Wave 110I session 13.

* Fleshwrither: Transfigure {2}{B}{B} (702.71a): sacrifice, search for a creature with the same mana value as the sacrificed creature (608.2h last known information).
* Monastery Raid: freerunning {X}{R} (702.173a; X in an alternative cost, 107.3a); "if this spell's freerunning cost was paid, exile the top X cards instead".
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import token_of
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave43d_cast_keywords import alt_key, connect
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
)
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

EXTRA = [
    real("Monastery Raid", "{2}{R}", 3, "Sorcery",
         "Freerunning {X}{R} (You may cast this spell for its freerunning cost if you dealt combat damage to a player this turn with an Assassin or commander.)\n"
         "Exile the top two cards of your library. If this spell's freerunning cost was paid, exile the top X cards of your library instead. You may play the exiled cards until the end of your next turn.",
         None, "R"),
    real("Fleshwrither", "{2}{B}{B}", 4, "Creature \u2014 Horror",
         "Transfigure {1}{B}{B} ({1}{B}{B}, Sacrifice this creature: Search your library for a creature card with the same mana value as this creature, put that card onto the battlefield, then shuffle. Transfigure only as a sorcery.)",
         ("3", "3"), "B"),
    real("Wolf110I", "{3}{G}", 4, "Creature \u2014 Wolf", "", ("4", "4"), "G"),
    real("Cub110I", "{1}{G}", 2, "Creature \u2014 Wolf", "", ("2", "2"), "G"),
]
_BASE.extend(EXTRA)


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def exiled(s):
    return len(s.state.zones.get("p1:exile", []))


def test_monastery_raid_normal_cast_exiles_two(cards):
    """Cast for its mana cost: the top two cards."""
    s = build(cards, ["Monastery Raid"])
    c = to_hand(s, "Monastery Raid")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert exiled(s) == 2
    check(s)


def test_monastery_raid_freerun_exiles_x(cards):
    """Freerunning cost paid after an Assassin hit a player: X = 4 gives the top four."""
    s = build(cards, ["Monastery Raid"])
    assassin = token_of(s, "p1", "Hidden Blade", "Token Creature — Human Assassin", "2/2")
    to_hand(s, "Monastery Raid")
    key = alt_key(s, "Monastery Raid", "freerunning")
    connect(s, assassin)
    mana(s, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Monastery Raid").id, alt_cost=key, x_value=4)
    answer(s)
    assert exiled(s) == 4
    check(s)


def test_fleshwrither_transfigure_fetches_same_mana_value(cards):
    """{1}{B}{B}, sacrifice it (mana value 4): only the mana value 4 creature can be found; the mana value 2 one stays."""
    s = build(cards, ["Fleshwrither", "Cub110I", "Wolf110I"])
    f = put(s, "Fleshwrither")
    mana(s, B=2, C=1)
    act(s, "p1", type="activate_ability", card_id=f.id, ability=0)
    answer(s)
    assert zone_of(s, "Fleshwrither") == "p1:graveyard"
    assert zone_of(s, "Wolf110I") == "p1:battlefield" and zone_of(s, "Cub110I") == "p1:library"
    check(s)
