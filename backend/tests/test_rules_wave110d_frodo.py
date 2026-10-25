"""Wave 110D: Frodo, Sauron's Bane, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 113.10, 701.54c: "{B}{B}{B}: If Frodo is a Scout, it becomes a Halfling Rogue with "Whenever this creature deals combat damage to a player, that player loses the
  game if the Ring has tempted you four or more times this game. Otherwise, the Ring tempts you."" — a Citizen first becomes a Scout; only a Scout becomes the
  Rogue; the Rogue tempts you for its first four hits (the Ring tempting you four times) and the damaged player loses the game on the next hit.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import activate, card_db, check, full, mana, now, put_new, settle, to_phase  # noqa: F401

FRODO = "Frodo, Sauron's Bane"


def attack(s, frodo, turn):
    to_phase(s, "declare_attackers", turn=turn)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": frodo.id, "target": "p2"}])
    for _ in range(80):
        d = s.state.rules.decision
        if s.state.rules.winner or s.state.turn.phase == "main2" and d is None and not s.state.zones.get("stack"):
            return
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            ids.sort(key=lambda i: i != frodo.id)  # (Frodo is the Ring-bearer; anything else: the first options)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def test_frodo_is_full():
    assert full(FRODO)


def test_rogue_tempts_three_times_then_the_damaged_player_loses(cards):
    s = build(cards, [FRODO])
    frodo = put_new(s, FRODO)
    to_phase(s, "main1", turn=3)
    mana(s, B=3)
    activate(s, frodo, "{B}{B}{B}:")  # (still a Citizen: nothing happens)
    assert not now(s, frodo).counters
    mana(s, B=2)
    activate(s, frodo, "{W/B}{W/B}:")
    mana(s, B=3)
    activate(s, frodo, "{B}{B}{B}:")
    for tempted, turn in ((1, 3), (2, 5), (3, 7), (4, 9)):
        attack(s, frodo, turn)
        assert s.state.rules.ring_tempted.get("p1") == tempted and "p2" not in s.state.rules.lost
    attack(s, frodo, 11)  # (the Ring has now tempted p1 four times)
    assert "p2" in s.state.rules.lost and s.state.rules.winner == "p1"
    check(s)
