"""Wave 110D: Hot Pursuit, real Oracle text (tests/fixtures/wave110d_cards.json), at a four-player table.

* 701.60a, 701.15a, 611.2b: the creature is suspected and goaded (by the Enchantment's controller) for as long as the Enchantment stays.
* 603.4: "if two or more players have lost the game" (checked at the trigger and as it resolves); then gain control of all goaded and/or suspected
  creatures until end of turn, untap them, haste (613.1b/613.4).
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable
from tests.wave9c_kit import to_hand
from tests.wave110d_kit import card_db, check, cost, full, mana, next_turn, now, put_new, settle  # noqa: F401

NAME = "Hot Pursuit"


def four(cards, mine, theirs):
    def d(cmdr, names, basic):
        return deck(cards, cmdr, [*((1, n) for n in names), (10, basic)])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=d("Krenko, Mob Boss", mine, "Forest")),
                                     PlayerSetup("Bob", cards=d("Atraxa, Praetors' Voice", theirs, "Island")),
                                     PlayerSetup("Carol", cards=d("Atraxa, Praetors' Voice", [], "Island")),
                                     PlayerSetup("Dave", cards=d("Atraxa, Praetors' Voice", [], "Island"))], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_full():
    assert full(NAME)


@pytest.mark.parametrize("lost", [1, 2])
def test_steal_needs_two_lost_players(cards, lost):
    s = four(cards, [NAME], ["Grizzly Bears"])
    bear = put_new(s, "Grizzly Bears", "p2")
    c = to_hand(s, NAME)
    mana(s, "p1", **cost(NAME))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s, answers=[bear.id])
    assert s.state.rules.object_id(bear.id) in s.state.rules.suspected
    for p in ("p3", "p4")[:lost]:
        act(s, p, type="concede")
    for _ in range(300):  # to the controller's next second main phase; the goaded creature must attack a player other than p1 (701.15b)
        d = s.state.rules.decision
        if s.state.turn.number > 1 and s.state.turn.active_player == "p1" and s.state.turn.phase == "main2":
            break
        if d is not None and d.kind == "declare_attackers" and d.player == "p2":
            foe = "p4" if lost == 1 else "p1"  # (701.15b: another player if able; here only the goader is left)
            act(s, "p2", type="declare_attackers", attackers=[{"card_id": bear.id, "target": foe}])
        elif d is not None and d.kind == "declare_attackers" and now(s, bear).controller == d.player:  # (stolen: goaded by p1, so it attacks another player)
            act(s, d.player, type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
        elif d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert (now(s, bear).controller == "p1") == (lost == 2)
    check(s)
