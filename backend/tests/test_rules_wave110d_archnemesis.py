"""Wave 110D: Archnemesis, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 508.1, 701.3, 303.4: "Whenever you attack enchanted player, ..." drains 2 and draws; "Whenever a player attacks you, you may attach this Aura to that player" moves it.
"""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable
from tests.wave9c_kit import build, life, put
from tests.wave110d_kit import card_db, check, full, now, put_new, settle, to_phase  # noqa: F401


def test_archnemesis_is_full():
    assert full("Archnemesis")


def test_attacking_enchanted_player_drains(cards):
    s = build(cards, ["Archnemesis", "Grizzly Bears"], [])
    arch = put_new(s, "Archnemesis")
    act(s, "p1", type="attach", card_ids=[arch.id], to="p2")
    bears = put_new(s, "Grizzly Bears")
    to_phase(s, "declare_attackers", turn=3)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    settle(s)
    assert life(s, "p2") == 36 and life(s, "p1") == 42 and len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def three(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Archnemesis"), (10, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    carol = deck(cards, "Atraxa, Praetors' Voice", [(1, "Grizzly Bears"), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_attacker_gets_the_aura(cards):
    s = three(cards)
    arch = put(s, "Archnemesis")
    act(s, "p1", type="attach", card_ids=[arch.id], to="p2")
    bears = put(s, "Grizzly Bears", pid="p3")
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p3", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    settle(s)
    assert now(s, arch).attached_player == "p3"
    check(s)
