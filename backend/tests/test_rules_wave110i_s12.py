"""Wave 110I session 12: draft-matters creatures in a game with no draft (905.2, 103.6): nothing was noted, removed or drafted.

* "enters with X +1/+1 counters, where X is the highest number you noted / the number of cards you removed from the draft": X is 0, no counters (Pyretic Hunter, Lurking Automaton, Cogwork Grinder).
* Ob Nixilis of the Black Oath: the -8 emblem's activated ability works from the command zone (114.4); X is the sacrificed creature's last known power (608.2h).
* Aether Searcher's enter trigger searches for a noted name: none was noted, nothing is found or cast (shared do-nothing primitive nothing_drafted110f, wave 110F).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave7c_counters import counters
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, check, life, mana, put

_REV = "Reveal this card as you draft it and note how many cards you've drafted this draft round, including this card.\n"
_X = "This creature enters with X +1/+1 counters on it, where X is the highest number you noted for cards named {n}."
EXTRA = [
    real("Pyretic Hunter", "{4}{R}", 5, "Creature — Elemental Cat", _REV + "Menace (This creature can't be blocked except by two or more creatures.)\n" + _X.format(n="Pyretic Hunter"), ("0", "0"), "R"),
    real("Lurking Automaton", "{5}", 5, "Artifact Creature — Construct", _REV + _X.format(n="Lurking Automaton"), ("0", "0")),
    real("Cogwork Grinder", "{6}", 6, "Artifact Creature — Construct",
         "Draft this card face up.\nAs you draft a card, you may remove it from the draft face down. (Those cards aren't in your card pool.)\n"
         "This creature enters with X +1/+1 counters on it, where X is the number of cards you removed from the draft with cards named Cogwork Grinder.", ("0", "0")),
    real("Aether Searcher", "{7}", 7, "Artifact Creature — Construct",
         "Reveal this card as you draft it. Reveal the next card you draft and note its name.\nWhen this creature enters, you may search your hand and/or library for a card with a name noted as you "
         "drafted cards named Aether Searcher. You may cast it without paying its mana cost. If you search your library this way, shuffle.", ("6", "4")),
    real("Ob Nixilis of the Black Oath", "{3}{B}{B}", 5, "Legendary Planeswalker \u2014 Nixilis",
         "+2: Each opponent loses 1 life. You gain life equal to the life lost this way.\n\u22122: Create a 5/5 black Demon creature token with flying. You lose 2 life.\n"
         "\u22128: You get an emblem with \"{1}{B}, Sacrifice a creature: You gain X life and draw X cards, where X is the sacrificed creature's power.\"\n"
         "Ob Nixilis of the Black Oath can be your commander.", None, "B"),
    real("Bear110I", "{1}{G}", 2, "Creature \u2014 Bear", "", ("3", "3"), "G"),
]
_BASE.extend(EXTRA)


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name,cost", [("Pyretic Hunter", dict(R=1, C=4)), ("Lurking Automaton", dict(C=5)), ("Cogwork Grinder", dict(C=6))])
def test_enters_with_no_counters(cards, name, cost):
    """X is 0: it enters as a 0/0 with no counters (and so dies to state-based actions, 704.5f)."""
    s = build(cards, [name])
    mana(s, "p1", **cost)
    cast(s, name)
    answer(s)
    c = next(c for c in s.state.cards.values() if c.name == name)
    assert not counters(s, c) and c.zone == "p1:graveyard"
    check(s)


def test_aether_searcher_finds_nothing(cards):
    """No name was noted: the enter trigger does nothing, the 6/4 stays and the stack empties."""
    s = build(cards, ["Aether Searcher"])
    mana(s, "p1", C=7)
    cast(s, "Aether Searcher")
    answer(s)
    c = next(c for c in s.state.cards.values() if c.name == "Aether Searcher")
    assert c.zone == "p1:battlefield" and not s.state.rules.stack
    check(s)


def test_ob_nixilis_emblem_sacrifice_gains_and_draws_power(cards):
    s = build(cards, ["Ob Nixilis of the Black Oath", "Bear110I"])
    ob, bear = put(s, "Ob Nixilis of the Black Oath"), put(s, "Bear110I")
    act(s, "p1", type="counter", card_ids=[ob.id], kind="loyalty", delta=8)
    act(s, "p1", type="activate_ability", card_id=ob.id, ability=2)
    answer(s)
    emblem = next(c for c in s.state.cards.values() if c.zone == "p1:command" and c.token is not None and c.token.type_line == "Emblem")
    mana(s, B=1, C=1)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=emblem.id, ability=0, cost_choices=[{"component": 1, "cards": [bear.id]}])
    answer(s)
    assert life(s, "p1") == 43 and len(s.state.zones["p1:hand"]) == hand + 3 and s.state.cards[bear.id].zone == "p1:graveyard"
    check(s)
