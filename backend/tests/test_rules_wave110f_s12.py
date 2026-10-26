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
from tests.test_rules_wave34b_activated import activate
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, check, life, mana, put, to_hand
from tests.wave36a_kit import ready

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
   """
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


def test_vapors_multicolored_card_goes_to_manual_play(cards):
    """105.2b: no rule or ruling settles one multicolored card serving several colors: a hand with one is resolved by hand, nothing is discarded."""
    s = build(cards, ["Noxious Vapors", "Test White 110F", "Test Gold 110F", "Test Blue 110F"])
    for n in ("Test White 110F", "Test Gold 110F", "Test Blue 110F"):
        to_hand(s, n)
    mana(s, "p1", B=2, C=1)
    cast(s, "Noxious Vapors")
    d = s.state.rules.decision
    assert d.kind == "manual_resolution" and d.player == "p1"
    answer(s, "done")
    assert all(_zone(s, n, "p1") == ["hand"] for n in ("Test White 110F", "Test Gold 110F", "Test Blue 110F"))
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


_EQUITY = ("As this enchantment enters, choose black or red.\nAt the beginning of your upkeep, sacrifice this enchantment unless you pay {1}{W}.\n"
           "Whenever a creature of the chosen color deals damage to you or a white creature you control, this enchantment deals that much damage to that creature.")
_ADD3 = [
    real("Mangara's Equity", '{2}{W}', 3, 'Enchantment', _EQUITY, None, 'W'),
    real('Test Red Atk 110F', '{2}{R}', 3, 'Creature — Giant', '', ('3', '5'), 'R'),
    real('Test Black Atk 110F', '{2}{B}', 3, 'Creature — Giant', '', ('3', '5'), 'B'),
    real('Test White Guard 110F', '{3}{W}', 4, 'Creature — Giant', '', ('1', '6'), 'W'),
    real('Test Black Guard 110F', '{3}{B}', 4, 'Creature — Giant', '', ('1', '6'), 'B'),
]
_BASE.extend(_ADD3)


def test_equity_full(cards):
    assert coverage.of_card_data(cards.resolve("Mangara's Equity")).level == "FULL"


@pytest.mark.parametrize("attacker,guard,hit", [
    ("Test Red Atk 110F", None, True),  # damage to you
    ("Test Red Atk 110F", "Test White Guard 110F", True),  # damage to a white creature you control
    ("Test Red Atk 110F", "Test Black Guard 110F", False),  # a non-white creature
    ("Test Black Atk 110F", None, False),  # not the chosen color
    ("Test Black Atk 110F", "Test White Guard 110F", False)])
def test_equity_returns_damage_to_chosen_color_creature(cards, attacker, guard, hit):
    """603.2, 120.3: the chosen color (Red) creature that damages Bob or his white creature takes that much damage from the enchantment."""
    from tests.test_rules_wave34b_activated import attack, block
    from tests.wave36a_kit import ready

    s = build(cards, [attacker], ["Mangara's Equity", *([guard] if guard else [])])
    eq = put(s, "Mangara's Equity", "p2")
    act(s, "p2", type="set_choice", card_id=eq.id, key="Chosen color", value="Red")
    atk = put(s, attacker)
    ready(s, attacker)
    if guard:
        g = put(s, guard, "p2")
    attack(s, atk)
    if guard:
        block(s, (g, atk))
    answer(s)
    dealt = s.state.cards[atk.id].damage
    assert dealt == (3 if hit else 0) + (1 if guard else 0)  # the guard hits back for 1
    check(s)


def test_equity_entering_choice_offers_only_black_or_red(cards):
    """614.12a: "choose black or red" is a color choice limited to those two."""
    s = build(cards, ["Mangara's Equity"])
    mana(s, "p1", W=1, C=2)
    cast(s, "Mangara's Equity")
    d = s.state.rules.decision
    assert sorted(o.id for o in d.options) == ["Black", "Red"]
    answer(s, "Black")
    eq = next(c for c in s.state.cards.values() if c.name == "Mangara's Equity")
    assert s.state.cards[eq.id].choices["Chosen color"] == "Black"
    check(s)


_ADD4 = [
    real('Peace Talks', '{1}{W}', 2, 'Sorcery',
         "This turn and next turn, creatures can't attack, and players and permanents can't be the targets of spells or activated abilities.", None, 'W'),
    real('Test Bolt 110F', '{R}', 1, 'Instant', "Test Bolt 110F deals 1 damage to any target.", None, 'R'),
    real('Test Pinger 110F', '{1}{R}', 2, 'Creature — Human', "When this creature enters, it deals 1 damage to any target.", ('1', '1'), 'R'),
    real('Test Tapper 110F', '{1}', 1, 'Artifact', "{T}: Test Tapper 110F deals 1 damage to any target.", None, ''),
]
_BASE.extend(_ADD4)


def _talks(cards, mine=(), theirs=()):
    s = build(cards, ["Peace Talks", "Test Bolt 110F", "Test Pinger 110F", "Test Tapper 110F", "Grizzly Bears", *mine], ["Grizzly Bears", *theirs])
    mana(s, "p1", W=1, C=1)
    cast(s, "Peace Talks")
    answer(s)
    return s


def test_peace_talks_full(cards):
    assert coverage.of_card_data(cards.resolve("Peace Talks")).level == "FULL"


def test_peace_talks_spells_and_activated_abilities_cannot_target_but_triggers_can(cards):
    """115.2: no spell or activated ability may target a player or permanent (this turn and the next); a triggered ability still can."""
    s = _talks(cards)
    bears = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Test Bolt 110F")
    mana(s, "p1", R=3, C=1)
    for target in ("p2", bears.id):
        with pytest.raises(ActionError):
            cast(s, "Test Bolt 110F", [target])
    tapper = put(s, "Test Tapper 110F")
    ready(s, "Test Tapper 110F")
    with pytest.raises(ActionError):
        activate(s, "p1", tapper, "", targets=["p2"])
    cast(s, "Test Pinger 110F")
    answer(s, "p2")
    assert life(s, "p2") == 39  # the enters trigger chose its target (603.3d)
    check(s)


def test_peace_talks_creatures_cannot_attack_this_turn_or_next_but_can_after(cards):
    from tests.test_rules_wave100f_attached import to_phase

    s = build(cards, ["Peace Talks", "Grizzly Bears"], ["Grizzly Bears"])
    mana(s, "p1", W=1, C=1)
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    ready(s, "Grizzly Bears")
    cast(s, "Peace Talks")
    answer(s)
    n = s.state.turn.number
    to_phase(s, "declare_attackers", turn=n)  # no creature can attack: the step is skipped, nothing to declare
    assert s.state.turn.phase != "declare_attackers"
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": mine.id, "target": "p2"}])
    to_phase(s, "declare_attackers", turn=n + 1)  # the next turn is p2's
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": theirs.id, "target": "p1"}])
    to_phase(s, "declare_attackers", turn=n + 2)  # then both are free again
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": mine.id, "target": "p2"}])
    check(s)


_ADD5 = [
    real('Swooping Pteranodon', '{3}{R}{W}', 5, 'Creature — Dinosaur',
         "Flying, haste\nWhenever this creature or another Dinosaur you control with flying enters, gain control of target creature an opponent controls until end of turn. "
         "Untap that creature. It gains flying and haste until end of turn. At the beginning of the next end step, target land deals 3 damage to that creature.", ('3', '3'), 'RW'),
    real('Test Reflexer 110F', '{1}{R}', 2, 'Creature — Human',
         "When this creature enters, you may sacrifice a creature. When you do, this creature deals 1 damage to any target.", ('1', '1'), 'R'),
]
_BASE.extend(_ADD5)


def test_peace_talks_delayed_and_reflexive_triggers_can_target(cards):
    """115.2: only spells and activated abilities are barred; an enters trigger, its delayed trigger (603.7) and a reflexive trigger (603.12) still target."""
    for n in ("Swooping Pteranodon", "Test Reflexer 110F"):
        assert coverage.of_card_data(cards.resolve(n)).level == "FULL"
    s = _talks(cards, mine=("Swooping Pteranodon",), theirs=("Forest",))
    put(s, "Forest", "p2")
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, "p1", R=1, W=1, C=3)
    cast(s, "Swooping Pteranodon")
    answer(s, bears.id)  # the enters trigger targets a creature
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    while s.state.rules.decision is None and s.state.turn.phase != "end":
        act(s, s.state.rules.priority, type="pass_priority")
    answer(s)  # the delayed trigger picks the only land
    assert s.state.cards[bears.id].zone == "p2:graveyard"  # 3 damage from the land, chosen as the trigger was put
    s = _talks(cards, mine=("Test Reflexer 110F",))
    put(s, "Grizzly Bears")
    mana(s, "p1", R=1, C=1)
    cast(s, "Test Reflexer 110F")
    answer(s, "pay", None, "p2")
    assert life(s, "p2") == 39  # the reflexive trigger chose its target
    check(s)
