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
from tests.wave9c_kit import build, check, life, mana, put, to_hand

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


_WORMS = ("Players can't play lands.\nLands can't enter the battlefield.\nAt the beginning of each upkeep, any player may sacrifice two lands of their choice or have this enchantment deal 5 damage to that player. "
          "If a player does either, destroy this enchantment.")
_ADD2 = [
    real('Worms of the Earth', '{2}{B}{B}', 4, 'Enchantment', _WORMS, None, 'B'),
    real('Test Ramp 110F', '{G}', 1, 'Sorcery', 'Put a land card from your hand onto the battlefield.', None, 'G'),
]
_BASE.extend(_ADD2)


def _upkeep(cards):
    from tests.test_rules_wave100f_attached import to_phase

    s = build(cards, ["Worms of the Earth", "Test Ramp 110F", "Test Land 110F"], ["Test Land 110F"])
    put(s, "Worms of the Earth")
    for pid in ("p1", "p2"):
        ids = [c.id for c in s.state.cards.values() if c.name == ("Forest" if pid == "p1" else "Island") and c.owner == pid][:3]
        act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "battlefield"})
    to_phase(s, "upkeep", turn=s.state.turn.number + 1)
    return s


def test_worms_full(cards):
    assert coverage.of_card_data(cards.resolve("Worms of the Earth")).level == "FULL"


def test_worms_lands_cannot_be_played_or_enter(cards):
    """305.1 / 614.17: no land play; a land another spell would put onto the battlefield stays in hand."""
    s = build(cards, ["Worms of the Earth", "Test Ramp 110F", "Test Land 110F"])
    put(s, "Worms of the Earth")
    land = to_hand(s, "Test Land 110F")
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=land.id)
    to_hand(s, "Test Ramp 110F")
    mana(s, "p1", G=1)
    cast(s, "Test Ramp 110F")
    answer(s)
    assert s.state.cards[land.id].zone == "p1:hand"
    check(s)


@pytest.mark.parametrize("p2,p1,survives", [("no", "no", True), ("sac", "no", False), ("hit", "no", False), ("no", "hit", False), ("sac", "sac", False)])
def test_worms_any_player_pays_or_takes_damage_to_destroy_it(cards, p2, p1, survives):
    """118.12: the active player (p2) answers first, then p1; a sacrifice (two lands) or 5 damage destroys it once; both saying no leaves it."""
    s = _upkeep(cards)
    nc = next(c for c in s.state.cards.values() if c.name == "Worms of the Earth")
    for pid, pick in (("p2", p2), ("p1", p1)):
        d = s.state.rules.decision
        while d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            d = s.state.rules.decision
        assert d.player == pid
        act(s, pid, type="choose", decision_id=d.id, option_ids=[pick])
    answer(s)
    assert (s.state.cards[nc.id].zone == "p1:battlefield") is survives
    forests = sum(1 for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:battlefield")
    forests2 = sum(1 for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:battlefield")
    assert (forests, forests2) == (3 - (2 if p1 == "sac" else 0), 3 - (2 if p2 == "sac" else 0))
    assert life(s, "p2") == 40 - (5 if p2 == "hit" else 0) and life(s, "p1") == 40 - (5 if p1 == "hit" else 0)
    check(s)
