"""-- drag to cast -- a permanent spell dragged from the hand onto its caster's battlefield enters where it was dropped (the cast intent's x, y,
kept with the spell on the stack, ``RulesState.cast_spots``), as a land played by a drag does. A permanent that enters someone else's
battlefield (Xantcha, 110.2) takes that table's usual free spot. Real Oracle text (Scryfall); each scenario checks the replay and a save
and a load (the spot is recorded in the resolve_top step)."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave110c_kit import answer, build, check, make_db, mana, real

EXTRA = [
    real("Xantcha, Sleeper Agent", "{2}", 2, "Legendary Artifact Creature — Phyrexian Assassin",
         "Xantcha enters under the control of an opponent of your choice.\nXantcha attacks each combat if able and can't attack its owner or planeswalkers its "
         "owner controls.\n{3}: Xantcha's controller loses 2 life and you draw a card. Any player may activate this ability.", ("2", "2"), ""),
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def _named(s, name):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == "p1")


def _cast(s, name, **at):
    card = _named(s, name)
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=card.id, **at)
    answer(s)
    return s.state.cards[card.id]


def test_a_dropped_creature_enters_where_it_was_dropped(cards):
    s = build(cards, ["Grizzly Bears"])
    mana(s, "p1", G=1, C=1)
    bears = _cast(s, "Grizzly Bears", x=612.5, y=340.0)
    assert bears.zone == "p1:battlefield" and (bears.x, bears.y) == (612.5, 340.0)
    assert s.state.rules.cast_spots == {}  # (used up as it resolved)
    check(s)


def test_the_spot_survives_the_tap_your_mana_prompt(cards):
    """At the table a drag usually opens the payment prompt first (players tap their own mana): the spot comes back with the intent."""
    s = build(cards, ["Grizzly Bears"])
    for prefs in s.state.rules.prefs.values():
        prefs.payment = "self"
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]
    for f in forests:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    bears = _named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=bears.id, x=612.5, y=340.0)
    d = s.state.rules.decision
    assert d is not None and (d.display or {}).get("kind") == "tap_mana"  # (paused for the payment)
    for f in forests:
        act(s, "p1", type="activate_ability", card_id=f.id, ability=0, tap_for_mana=True)
    answer(s)
    bears = s.state.cards[bears.id]
    assert bears.zone == "p1:battlefield" and (bears.x, bears.y) == (612.5, 340.0)
    check(s)


def test_without_a_spot_it_takes_the_usual_free_spot(cards):
    s = build(cards, ["Grizzly Bears"])
    mana(s, "p1", G=1, C=1)
    bears = _cast(s, "Grizzly Bears")
    assert bears.zone == "p1:battlefield" and (bears.x, bears.y) != (612.5, 340.0)
    check(s)


def test_a_spell_entering_an_opponents_battlefield_ignores_the_drop_spot(cards):
    s = build(cards, ["Xantcha, Sleeper Agent"])
    mana(s, "p1", C=2)
    xantcha = _cast(s, "Xantcha, Sleeper Agent", x=612.5, y=340.0)
    assert xantcha.zone == "p2:battlefield" and (xantcha.x, xantcha.y) != (612.5, 340.0)  # (the drop spot was on Alice's side)
    assert s.state.rules.cast_spots == {}
    check(s)
