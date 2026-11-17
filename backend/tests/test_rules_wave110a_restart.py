"""Wave 110A: Karn Liberated (727 restarting the game; rulings 2020-08-07; Commander 903.8, 903.9 still apply in the new game)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.mulligan import COMMANDER_LONDON
from app.rules import coverage
from tests.wave53d_kit import table
from tests.wave110a_kit import *

KARN = "Karn Liberated"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def _game(cards, policy=None, exiled="Grizzly Bears", decline=False):
    """Bob (p2) controls Karn. Turn 2: -3 exiles Alice's Grizzly Bears. Turn 5: +4, Carol exiles Pacifism (an Aura). Then Karn is at 14."""
    s = table(cards, mine=["Grizzly Bears", "Lightning Bolt"], bobs=[KARN, "Llanowar Elves"], carols=["Pacifism", "Grizzly Bears"])
    karn, bears = put(s, KARN, "p2"), put(s, exiled)
    to_hand(s, "Pacifism", "p3")
    act(s, "p1", type="counter", card_ids=[karn.id], kind="loyalty", delta=6)
    to_phase(s, "main1", 2)
    act(s, "p2", type="activate_ability", card_id=karn.id, ability=1, targets=[bears.id])
    answer(s, *(["no"] if decline else []))  # 903.9a: a commander's owner may put it into the command zone instead
    assert s.state.cards[bears.id].zone == "p1:exile"
    to_phase(s, "main1", 5)
    act(s, "p2", type="activate_ability", card_id=karn.id, ability=0, targets=["p3"])
    answer(s)
    assert card_named(s, "Pacifism", "p3").zone == "p3:exile"
    act(s, "p1", type="counter", card_ids=[karn.id], kind="loyalty", delta=14 - s.state.cards[karn.id].counters.get("loyalty", 0))  # (the table tool: the loyalty cost of the real activations is paid)
    s.state.settings.mulligan = policy
    s.state.players["p1"].commander_tax = {k: 2 for k in s.state.players["p1"].commander_tax}
    s.state.players["p1"].commander_damage = {"x": 5}
    to_phase(s, "main1", 8)
    return s, karn, bears


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(KARN)).level == "FULL"


def test_restart_without_mulligans(cards):
    s, karn, bears = _game(cards)
    pacifism = card_named(s, "Pacifism", "p3")
    act(s, "p2", type="activate_ability", card_id=karn.id, ability=2)
    answer(s)
    assert s.state.turn.number == 1 and s.state.turn.active_player == "p2"  # 727.1a: the controller of the ability starts
    assert s.state.cards[karn.id].zone in ("p2:library", "p2:hand")  # (shuffled, then 7 drawn)  # 727.2: Karn goes back into his owner's deck
    assert s.state.cards[pacifism.id].zone in ("p3:library", "p3:hand")  # an Aura is not left in exile
    assert (s.state.cards[bears.id].zone, s.state.cards[bears.id].owner, s.state.cards[bears.id].controller) == ("p2:battlefield", "p1", "p2")  # 727.4, ruling
    # S7: the new game doesn't wait in its untap step (502.4): on through upkeep and the draw step (three players: nobody skips it, 103.8c)
    assert (s.state.turn.phase, s.state.rules.priority) == ("main1", "p2")
    for pid in ("p1", "p2", "p3"):
        drew = 1 if pid == "p2" else 0
        assert s.state.players[pid].life == 40 and len(s.state.zones[f"{pid}:hand"]) == 7 + drew and s.state.players[pid].commander_damage == {}
        assert [s.state.cards[c].commander_key is not None for c in s.state.zones[f"{pid}:command"]] == [True]  # 903.8: the commanders are back
    assert set(s.state.players["p1"].commander_tax.values()) == {0}
    assert s.state.rules.controlled_since[bears.id].turn == 0  # under their control since the beginning of the first turn: it may attack
    assert not s.state.zones["stack"] and s.state.rules.winner is None
    check(s)


def test_restart_with_mulligans_the_kept_cards_enter_after_them(cards):
    s, karn, bears = _game(cards, COMMANDER_LONDON)
    act(s, "p2", type="activate_ability", card_id=karn.id, ability=2)
    answer(s)
    assert s.state.pregame is not None and not s.state.pregame.finished and s.state.turn.active_player == "p2"
    assert s.state.cards[bears.id].zone == "p1:exile"  # 727.4: not before the mulligans are over
    check(s)
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="mulligan_keep")
    answer(s)  # the opening-hand question (103.6) of each player in turn: nothing to use
    assert s.state.pregame.finished and s.state.cards[bears.id].zone == "p2:battlefield" and s.state.cards[bears.id].owner == "p1"
    assert s.state.rules.controlled_since[bears.id].turn == 0
    check(s)
    act(s, "p2", type="pass_priority")  # the new game plays on
    assert s.state.turn.number == 1


def test_a_commander_exiled_with_karn_stays_exiled_and_stays_the_commander(cards):
    s, karn, krenko = _game(cards, exiled="Krenko, Mob Boss", decline=True)
    key = krenko.commander_key
    act(s, "p2", type="activate_ability", card_id=karn.id, ability=2)
    answer(s)
    c = s.state.cards[krenko.id]
    assert (c.zone, c.commander_key) == ("p2:battlefield", key)  # 727.5a: not in the command zone, but still p1's commander
    assert s.state.zones["p1:command"] == []
    check(s)


def test_a_player_who_left_the_game_is_not_in_the_new_one(cards):
    s, karn, bears = _game(cards)
    act(s, "p3", type="concede")
    act(s, "p2", type="activate_ability", card_id=karn.id, ability=2)
    answer(s)
    assert s.state.rules.conceded == ["p3"] and s.state.turn.active_player == "p2"
    assert len(s.state.zones["p1:hand"]) == len(s.state.zones["p2:hand"]) == 7 and len(s.state.zones["p3:hand"]) < 7
    check(s)
