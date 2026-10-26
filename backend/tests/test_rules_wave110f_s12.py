"""Wave 110F session 12, on real Oracle text. Every scenario checks the replay and a save and a load.

* 614.12a, 201.4a: "As ~ enters, you and an opponent each choose a card name other than a basic land card name." (Null Chamber): two public names on the permanent.
* 601.3, 305.1: "Spells with the chosen names can't be cast and lands with the chosen names can't be played." (either name; other cards are unaffected).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, check, mana, to_hand

EXTRA = [
    real('Serra Angel', '{3}{W}{W}', 5, 'Creature — Angel', 'Flying, vigilance', ('4', '4'), 'W'),
    real('Test Land 110F', '', 0, 'Land', '{T}: Add {C}.', None, ''),
    real('Null Chamber', '{1}{W}{W}', 3, 'Enchantment',
         "As this enchantment enters, you and an opponent each choose a card name other than a basic land card name.\nSpells with the chosen names can't be cast and lands with the chosen names can't be played.", None, 'W'),
]
_BASE.extend(EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Null Chamber")).level == "FULL"


def _enter(cards, mine, theirs):
    s = build(cards, ["Null Chamber", "Grizzly Bears", "Llanowar Elves", "Forest", "Test Land 110F", "Serra Angel"], ["Grizzly Bears"])
    mana(s, "p1", W=2, C=1)
    cast(s, "Null Chamber")
    for pid, name in (("p1", mine), ("p2", theirs)):
        d = s.state.rules.decision
        assert d is not None and d.player == pid and d.options[0].id == "__name__"  # you name first, then the opponent
        act(s, pid, type="choose", decision_id=d.id, name=name)
    answer(s)
    return s


@pytest.mark.parametrize("name,legal", [("Grizzly Bears", False), ("Llanowar Elves", False), ("Serra Angel", True)])
def test_either_chosen_name_cannot_be_cast(cards, name, legal):
    """601.3: a spell with either chosen name can't be cast; any other card still can (one more card in hand)."""
    s = _enter(cards, "Grizzly Bears", "Llanowar Elves")
    nc = next(c for c in s.state.cards.values() if c.name == "Null Chamber")
    assert s.state.cards[nc.id].choices["Chosen card name"] == "Grizzly Bears | Llanowar Elves"
    to_hand(s, name)
    mana(s, "p1", G=1, W=3, C=2)
    if legal:
        cast(s, name)
    else:
        with pytest.raises(ActionError):
            cast(s, name)
    check(s)


@pytest.mark.parametrize("name,legal", [("Test Land 110F", False), ("Forest", True)])
def test_lands_with_either_chosen_name_cannot_be_played(cards, name, legal):
    """305.1: the opponent's name (a nonbasic land) bars lands too; a land with another name is played."""
    s = _enter(cards, "Grizzly Bears", "Test Land 110F")
    c = to_hand(s, name)
    if legal:
        act(s, "p1", type="play_land", card_id=c.id)
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="play_land", card_id=c.id)
    check(s)


def test_a_basic_land_name_cannot_be_chosen(cards):
    """201.4a: the opponent's name, like yours, is not a basic land card name."""
    s = build(cards, ["Null Chamber"], ["Grizzly Bears"])
    mana(s, "p1", W=2, C=1)
    cast(s, "Null Chamber")
    for pid, name in (("p1", "Grizzly Bears"), ("p2", "Forest")):
        d = s.state.rules.decision
        if pid == "p2":
            with pytest.raises(ActionError):
                act(s, pid, type="choose", decision_id=d.id, name=name)
            name = "Grizzly Bears"
        act(s, pid, type="choose", decision_id=d.id, name=name)
    answer(s)
    check(s)


_VAPORS = "Each player reveals their hand, chooses one card of each color from it, then discards all other nonland cards."
_ADD = [
    real('Noxious Vapors', '{1}{B}{B}', 3, 'Sorcery', _VAPORS, None, 'B'),
    real('Test White 110F', '{W}', 1, 'Creature — Human', '', ('1', '1'), 'W'),
    real('Test White B 110F', '{W}', 1, 'Creature — Human', '', ('1', '1'), 'W'),
    real('Test Gold 110F', '{W}{U}', 2, 'Creature — Human', '', ('1', '1'), 'WU'),
    real('Test Blue 110F', '{U}', 1, 'Creature — Human', '', ('1', '1'), 'U'),
    real('Test Relic 110F', '{2}', 2, 'Artifact', '', None, ''),
]
_BASE.extend(_ADD)


def test_vapors_full(cards):
    assert coverage.of_card_data(cards.resolve("Noxious Vapors")).level == "FULL"


def _zone(s, name, pid):
    return sorted(c.zone.split(":")[1] for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.split(":")[1] in ("hand", "graveyard"))


def test_vapors_each_player_keeps_one_card_of_each_color_and_all_lands(cards):
    """701.9, 105.2b: p1 keeps the picked white card, the blue card and the land; the other white card and the colorless artifact are discarded; p2 (one white card only) keeps it.
    A multicolored card chosen for white is blue as well, so blue needs no further pick."""
    s = build(cards, ["Noxious Vapors", "Test White 110F", "Test White B 110F", "Test Blue 110F", "Test Relic 110F", "Test Land 110F"], ["Test White 110F", "Test Relic 110F"])
    for n in ("Test White 110F", "Test White B 110F", "Test Blue 110F", "Test Relic 110F", "Test Land 110F"):
        to_hand(s, n)
    to_hand(s, "Test White 110F", "p2")
    to_hand(s, "Test Relic 110F", "p2")
    mana(s, "p1", B=2, C=1)
    cast(s, "Noxious Vapors")
    d = s.state.rules.decision
    assert d.player == "p1" and len(d.options) == 2  # white: two to pick from (blue has one: no question)
    answer(s, [next(o.id for o in d.options if s.state.cards[o.id].name == "Test White B 110F")])
    assert _zone(s, "Test White B 110F", "p1") == ["hand"] and _zone(s, "Test White 110F", "p1") == ["graveyard"]
    assert _zone(s, "Test Blue 110F", "p1") == ["hand"] and _zone(s, "Test Land 110F", "p1") == ["hand"] and _zone(s, "Test Relic 110F", "p1") == ["graveyard"]
    assert _zone(s, "Test White 110F", "p2") == ["hand"] and _zone(s, "Test Relic 110F", "p2") == ["graveyard"]
    check(s)


def test_vapors_multicolored_pick_covers_both_colors(cards):
    s = build(cards, ["Noxious Vapors", "Test White 110F", "Test Gold 110F", "Test Blue 110F"])
    for n in ("Test White 110F", "Test Gold 110F", "Test Blue 110F"):
        to_hand(s, n)
    mana(s, "p1", B=2, C=1)
    cast(s, "Noxious Vapors")
    d = s.state.rules.decision  # white: the white creature or the gold one
    answer(s, [next(o.id for o in d.options if s.state.cards[o.id].name == "Test Gold 110F")])
    assert _zone(s, "Test Gold 110F", "p1") == ["hand"] and _zone(s, "Test White 110F", "p1") == ["graveyard"] and _zone(s, "Test Blue 110F", "p1") == ["graveyard"]
    check(s)
