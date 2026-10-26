"""Wave 110D: Central Elevator // Promising Stairs, real Oracle text (tests/fixtures/wave110d_cards.json).

* 709.5h: Central Elevator's unlock trigger searches for a Room card sharing no name (201.2a) with a Room you control.
* 104.2b, 709.5: Promising Stairs wins the game at upkeep with eight or more different names among the unlocked doors (a Room with both unlocked has two).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave110d_kit import build, card_db, cast_on, check, full, hand_new, mana, now, put_new, settle, to_phase  # noqa: F401

NAME = "Central Elevator // Promising Stairs"
FUNERAL = "Funeral Room // Awakening Hall"
CLOSET = "Walk-In Closet // Forgotten Cellar"
OTHERS = [FUNERAL, "Experimental Lab // Staff Room", "Dollmaker's Shop // Porcelain Gallery", "Bottomless Pool // Locker Room", CLOSET]


def test_full():
    assert full(NAME)


def unlock(s, c, *doors):
    s.state.rules.unlocked[s.state.rules.object_id(c.id)] = list(doors)


def test_search_skips_a_room_sharing_a_name(cards):
    s = build(cards, [NAME, FUNERAL, FUNERAL, CLOSET], ["Grizzly Bears"])
    funeral = put_new(s, FUNERAL)
    unlock(s, funeral, 1)
    hand = hand_new(s, NAME)
    mana(s, "p1", C=3, U=1)
    act(s, "p1", type="cast_spell", card_id=hand.id, face=0)
    settle(s)
    got = [c.name for c in s.state.cards.values() if c.zone == "p1:hand" and c.owner == "p1"]
    assert CLOSET in got and got.count(FUNERAL) == 0
    check(s)


def _upkeep(cards, doors):
    """Promising Stairs unlocked, plus ``doors`` more unlocked doors on other Rooms, then p1's upkeep."""
    s = build(cards, [NAME, *OTHERS, *["Grizzly Bears"] * 25], ["Grizzly Bears"])  # (cards to draw)
    stairs = put_new(s, NAME)
    unlock(s, stairs, 2)
    for room in OTHERS:
        n = min(2, doors)
        if n:
            unlock(s, put_new(s, room), *range(1, n + 1))
        doors -= n
    for _ in range(80):  # (through turn 3's upkeep: surveil 1 takes the first option)
        d = s.state.rules.decision
        if s.state.rules.winner or (s.state.turn.number == 3 and s.state.turn.phase in ("draw", "main1")) or s.state.turn.number > 3:
            break
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return s


def test_eight_names_win(cards):
    s = _upkeep(cards, 7)
    assert s.state.rules.winner == "p1"
    check(s)


def test_seven_names_do_not(cards):
    s = _upkeep(cards, 6)
    assert not s.state.rules.winner
    check(s)
