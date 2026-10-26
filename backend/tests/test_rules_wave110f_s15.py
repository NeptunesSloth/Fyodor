"""Wave 110F session 15, on real Oracle text. Every scenario checks the replay and a save and a load.

* 111.2, 603.10a: Dance of Many: "the token" is the token its own enters ability created. The enchantment leaving exiles it; that token leaving
  (looking back, 603.10a) sacrifices the enchantment; another creature leaving does neither.
* 118.8: Drought never forbids an activation it does not tax (see test_rules_wave110f_s13).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, check, mana, put

_DANCE = ("When this enchantment enters, create a token that's a copy of target nontoken creature.\n"
          "When this enchantment leaves the battlefield, exile the token.\n"
          "When the token leaves the battlefield, sacrifice this enchantment.\n"
          "At the beginning of your upkeep, sacrifice this enchantment unless you pay {U}{U}.")
EXTRA = [
    real('Dance of Many', '{U}{U}{U}', 3, 'Enchantment', _DANCE, None, 'U'),
    real('Test Smite 110F', '{B}', 1, 'Instant', 'Destroy target creature.', None, 'B'),
    real('Test Disenchant 110F', '{W}', 1, 'Instant', 'Destroy target enchantment.', None, 'W'),
]
_MALIK = ("When Malik, Grim Manipulator enters, you and target opponent each secretly choose a creature that player controls. Then those choices are revealed, "
          "and that player sacrifices those creatures.\nWhenever an opponent sacrifices a creature, you create a Treasure token.")
EXTRA.append(real('Test Angel 110F', '{3}{W}{W}', 5, 'Creature — Angel', '', ('4', '4'), 'W'))
EXTRA.append(real('Malik, Grim Manipulator', '{2}{R}{W}{B}', 5, 'Legendary Creature — Human Rogue', _MALIK, ('4', '3'), 'BRW'))
_BASE.extend(EXTRA)


@pytest.mark.parametrize("name", ["Dance of Many", "Malik, Grim Manipulator"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _dance(cards):
    s = build(cards, ["Dance of Many", "Llanowar Elves", "Test Smite 110F", "Test Disenchant 110F"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    elf = put(s, "Llanowar Elves")
    mana(s, "p1", U=3, B=2, W=2)
    cast(s, "Dance of Many")
    answer(s, bears.id)
    token = next(c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield")
    dance = next(c for c in s.state.cards.values() if c.name == "Dance of Many")
    return s, dance, token, elf


def _zone(s, c):
    return s.state.cards[c.id].zone if c.id in s.state.cards else "gone"


def test_token_leaving_sacrifices_the_enchantment(cards):
    s, dance, token, _ = _dance(cards)
    assert token.name == "Grizzly Bears" and dance.zone == "p1:battlefield"
    cast(s, "Test Smite 110F", [token.id])
    answer(s)
    assert _zone(s, dance) == "p1:graveyard"
    check(s)


def test_enchantment_leaving_exiles_the_token(cards):
    s, dance, token, _ = _dance(cards)
    cast(s, "Test Disenchant 110F", [dance.id])
    answer(s)
    assert _zone(s, dance) == "p1:graveyard" and _zone(s, token) in ("gone", "p1:exile")
    check(s)


def test_another_creature_leaving_changes_nothing(cards):
    s, dance, token, elf = _dance(cards)
    cast(s, "Test Smite 110F", [elf.id])
    answer(s)
    assert _zone(s, elf) == "p1:graveyard" and _zone(s, dance) == "p1:battlefield" and _zone(s, token) == "p1:battlefield"
    check(s)


def _malik(cards, theirs):
    s = build(cards, ["Malik, Grim Manipulator"], theirs)
    mine = [put(s, n, "p2") for n in theirs]
    mana(s, "p1", R=1, W=1, B=1, C=2)
    cast(s, "Malik, Grim Manipulator")
    return s, mine


def _treasures(s):
    return sum(c.name == "Treasure" and c.zone == "p1:battlefield" for c in s.state.cards.values())


def test_malik_each_choose_in_secret_then_opponent_sacrifices_both(cards):
    """101.4c, 701.21a: you pick one of their creatures, they pick one of their own; both are sacrificed; a Treasure for each sacrifice."""
    s, (bears, elf, angel) = _malik(cards, ["Grizzly Bears", "Llanowar Elves", "Test Angel 110F"])
    answer(s, None, bears.id, elf.id)
    assert [_zone(s, c) for c in (bears, elf, angel)] == ["p2:graveyard", "p2:graveyard", "p2:battlefield"] and _treasures(s) == 2
    check(s)


def test_malik_same_creature_chosen_twice_is_sacrificed_once(cards):
    s, (bears, elf) = _malik(cards, ["Grizzly Bears", "Llanowar Elves"])
    answer(s, None, bears.id, bears.id)
    assert [_zone(s, c) for c in (bears, elf)] == ["p2:graveyard", "p2:battlefield"] and _treasures(s) == 1
    check(s)


def test_malik_the_choices_are_private(cards):
    """400.2: while the opponent chooses, you are shown only that they are choosing (and they never see your pick before the reveal)."""
    from app.rules.view import decision_view

    s, (bears, elf) = _malik(cards, ["Grizzly Bears", "Llanowar Elves"])
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["p2"])  # the target opponent
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {bears.id, elf.id}
    assert "options" not in decision_view(s.state, d, "p2")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    d = s.state.rules.decision
    assert d.player == "p2" and "options" not in decision_view(s.state, d, "p1")
