"""Wave 110M: simultaneous secret choices. 101.4: every player chooses (here: a number of items, 1 or more) before any is revealed; what the choices do happens afterwards.
Goblin Game: each player loses life equal to their number; then the player(s) who revealed the fewest lose half their (remaining) life, rounded up.
Every scenario checks the replay and a save and a load.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110m_kit import *

GAME = "Goblin Game"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([GAME])


def play(s, **numbers):
    """Cast the Game, then each player types their number in turn."""
    cast(s, GAME)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            return
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[], name=str(numbers[d.player]))
    raise AssertionError("never settled")


def test_the_fewest_loses_half_of_what_is_left(cards):
    s = build(cards, [GAME], ["Elite Vanguard"], forests=20)
    play(s, p1=3, p2=5)
    assert life(s, "p2") == 35  # (5 items, not the fewest)
    assert life(s) == 18  # (3 items: 40 - 3 = 37, then half of 37 rounded up is 19)
    check(s)


def test_players_tied_for_fewest_each_lose_half(cards):
    s = build(cards, [GAME], ["Elite Vanguard"], forests=20)
    play(s, p1=2, p2=2)
    assert life(s) == life(s, "p2") == 19  # (38, then half of 38)
    check(s)


def test_at_least_one_item_must_be_hidden(cards):
    s = build(cards, [GAME], ["Elite Vanguard"], forests=20)
    cast(s, GAME)
    d = s.state.rules.decision
    assert d is not None
    with pytest.raises(ActionError):
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[], name="0")
    check(s)


# -- _____ _____ Rocketship --------------------------------------------------------------------------------------------------------------------
ROCKET = "_____ _____ Rocketship"
test_rocket_full = full_test([ROCKET])


def rocket_attack(cards, names):
    """The Rocketship cast with its name stickers placed by its own enters trigger, crewed and attacking."""
    from app.game.factory import DeckCard, PlayerSetup, new_game
    from app.game.session import GameSession
    from app.rules.sticker_sheets101 import SHEETS
    from tests.game_helpers import deck, enable
    from tests.test_rules_sticker_effects101 import FixedSheetRng, place, question
    from tests.test_rules_sticker_effects101 import cast as cast101
    from tests.wave36a_kit import ready
    from tests.wave100c_kit import to_phase as to_phase100

    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), (1, ROCKET), (1, "Grizzly Bears")])
    wanted = ["Eldrazi Guacamole Tightrope", "Ancestral Hot Dog Minotaur", "Trendy Circus Pirate"]
    sheets = [sh for n in wanted for sh in SHEETS.values() if sh["name"] == n]
    mine += [DeckCard("stickers", 1, sh["name"], sh["printing_id"]) for sh in sheets]
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)], shuffle=False, rng=FixedSheetRng()))
    s = GameSession(state, cards=cards)
    for pid in state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase100(s, "main1", 1)
    ship = cast101(s, ROCKET)
    question(s)
    for k, text in enumerate(names):
        place(s, ship.id, "name", text=text, position=k)
        if k + 1 < len(names):
            question(s)
    answer(s)
    bears = put(s, "Grizzly Bears")
    ready(s, "Grizzly Bears")
    s.state.rules.controlled_since[ship.id].turn = 0
    index = next(a.index for a in ch(s, ship).abilities if a.text.lower().startswith("crew"))
    act(s, "p1", type="activate_ability", card_id=ship.id, ability=index, crew=[bears.id])
    answer(s)
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ship.id, "target": "p2"}])
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return s, ship


def pick_letter(s, letter):
    d = s.state.rules.decision
    assert d is not None and len(d.options) == 26
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[letter])
    answer(s)


def test_rocketship_grows_for_each_name_sticker_beginning_with_the_letter(cards):
    s, ship = rocket_attack(cards, ["Trendy", "Hot Dog"])
    pick_letter(s, "T")
    assert ch(s, ship).pt == (3, 4)  # (only "Trendy" begins with T: 2/3 +1/+1)
    check(s)


def test_a_letter_no_sticker_begins_with_changes_nothing(cards):
    s, ship = rocket_attack(cards, ["Trendy", "Hot Dog"])
    pick_letter(s, "Z")
    assert ch(s, ship).pt == (2, 3)
    check(s)


def test_the_letter_is_matched_whatever_its_case(cards):
    s, ship = rocket_attack(cards, ["Hot Dog"])
    pick_letter(s, "H")
    assert ch(s, ship).pt == (3, 4)
    check(s)


# -- Bend or Break -----------------------------------------------------------------------------------------------------------------------------
BEND = "Bend or Break"
test_bend_full = full_test([BEND])


def lands(s, pid):
    return [c for c in s.state.cards.values() if c.zone == f"{pid}:battlefield" and "Land" in ch(s, c).types]


def bend(cards, mine=4, theirs=2):
    s = build(cards, [BEND], ["Elite Vanguard"], forests=20, islands=20)
    for pid, n in (("p1", mine), ("p2", theirs)):
        for c in [c for c in s.state.cards.values() if c.owner == pid and c.zone == f"{pid}:library" and c.name in ("Forest", "Island")][:n]:
            act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s


def test_bend_or_break_destroys_the_chosen_piles_and_taps_the_others(cards):
    s = bend(cards)
    before = {pid: [c.id for c in lands(s, pid)] for pid in ("p1", "p2")}
    cast_first = to_hand(s, BEND)
    fund(s, "{3}{R}")
    act(s, "p1", type="cast_spell", card_id=cast_first.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_cards":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])  # a pile of one land, the rest in the other
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["1"])  # the opponent picks the first pile
    mine, theirs = lands(s, "p1"), lands(s, "p2")
    assert len(mine) == 3 and len(theirs) == 1  # (one land of each in the chosen piles destroyed)
    assert all(c.tapped for c in mine + theirs)  # (the other piles were tapped)
    assert {c.id for c in mine} <= set(before["p1"]) and {c.id for c in theirs} <= set(before["p2"])
    check(s)


def test_bend_or_break_with_three_players_each_owner_names_the_opponent_who_chooses(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [(1, BEND), (9, "Forest")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(9, "Island")])),
              PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(9, "Forest")]))]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    for pid in ("p1", "p2", "p3"):
        for c in [c for c in s.state.cards.values() if c.owner == pid and c.zone == f"{pid}:library" and c.name in ("Forest", "Island")][:2]:
            act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    c = to_hand(s, BEND)
    fund(s, "{3}{R}")
    act(s, "p1", type="cast_spell", card_id=c.id)
    named = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_cards":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        elif {o.id for o in d.options} <= {"p1", "p2", "p3"}:
            named.append((d.player, sorted(o.id for o in d.options)))  # the owner names the opponent who chooses
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[-1].id])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["2"])
    assert named == [("p1", ["p2", "p3"]), ("p2", ["p1", "p3"]), ("p3", ["p1", "p2"])]
    assert [len(lands(s, p)) for p in ("p1", "p2", "p3")] == [1, 1, 1]  # (the pile of one land destroyed, the other tapped)
    assert all(c.tapped for p in ("p1", "p2", "p3") for c in lands(s, p))
    check(s)
