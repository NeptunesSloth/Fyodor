"""Wave 46B: the Lace cycle (CR 2026-09-25, real Oracle text, tests/fixtures/wave46b_cards.json). Every scenario checks the replay and a save and a load.

* 105.3 / 613.1e: "Target spell or permanent becomes blue." replaces the object's colors (layer 5); mana symbols are not changed (105.3, 202.2).
* 611.2a: no duration stated: the effect lasts until the end of the game. 611.2c: it affects the objects it found as it resolved.
* 400.7a: what a spell does to a permanent spell goes on applying to the permanent it becomes (Moonlace ruling 2006-09-25: it enters colorless and
  stays colorless); an instant or sorcery spell that becomes a color is that color only on the stack.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave5j_token_copies import ok
from tests.test_rules_wave38a_trailing_ifs import table
from tests.wave9c_kit import card_named, check, mana, put, to_hand
from tests.wave36a_kit import resolve_stack
from tests.wave45c_kit import hold
from tests.wave46b_kit import make_repo, zone

LACES = {"Thoughtlace": "U", "Deathlace": "B", "Chaoslace": "R", "Purelace": "W", "Lifelace": "G", "Moonlace": None}


@pytest.fixture()
def cards(settings):
    repo = make_repo(settings)
    yield repo
    repo.close()


def ch(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id])


def colors(s, name, pid="p1"):
    return set(ch(s, name, pid).colors)


@pytest.mark.parametrize("name", LACES)
def test_the_lace_cycle_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_thoughtlace_turns_a_permanent_blue_for_good(cards):
    s = table(cards, ["Thoughtlace", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    to_hand(s, "Thoughtlace")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Thoughtlace").id, targets=[card_named(s, "Grizzly Bears").id])
    resolve_stack(s)
    assert colors(s, "Grizzly Bears") == {"U"}
    assert ch(s, "Grizzly Bears").mana_cost == "{1}{G}"  # (symbols unchanged)
    check(s)


def test_moonlace_makes_a_permanent_colorless(cards):
    s = table(cards, ["Moonlace", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    to_hand(s, "Moonlace")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Moonlace").id, targets=[card_named(s, "Grizzly Bears").id])
    resolve_stack(s)
    assert colors(s, "Grizzly Bears") == set()
    check(s)


def test_deathlace_on_a_permanent_spell_goes_on_to_the_permanent_it_becomes(cards):
    s = table(cards, ["Deathlace", "Grizzly Bears"])
    hold(s)
    to_hand(s, "Grizzly Bears")
    to_hand(s, "Deathlace")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Deathlace").id, targets=[card_named(s, "Grizzly Bears").id])
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="pass_priority")  # Deathlace resolves: the Bears spell is black
    assert zone(s, "Grizzly Bears") == "stack" and colors(s, "Grizzly Bears") == {"B"}
    resolve_stack(s)
    assert zone(s, "Grizzly Bears") == "p1:battlefield" and colors(s, "Grizzly Bears") == {"B"}  # (400.7a)
    check(s)


def test_chaoslace_on_a_sorcery_spell_does_nothing_lasting(cards):
    s = table(cards, ["Chaoslace", "Wrath of God"], ["Grizzly Bears"])
    hold(s)
    to_hand(s, "Wrath of God")
    to_hand(s, "Chaoslace")
    mana(s, W=2, B=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Wrath of God").id)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Chaoslace").id, targets=[card_named(s, "Wrath of God").id])
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="pass_priority")
    assert zone(s, "Wrath of God") == "stack" and colors(s, "Wrath of God") == {"R"}
    resolve_stack(s)
    assert zone(s, "Wrath of God") == "p1:graveyard" and colors(s, "Wrath of God") == {"W"}  # (400.7)
    check(s)


def test_a_color_with_a_rider_and_no_duration_is_still_refused():
    """"… becomes red and gains flying." with no duration: the keyword would need its own duration (611.2a), not read."""
    assert ok("Target creature becomes red.", "Card", "Sorcery")
    assert not ok("Target creature becomes red and gains flying.", "Card", "Sorcery")
    assert ok("Target creature becomes red and gains flying until end of turn.", "Card", "Sorcery")
