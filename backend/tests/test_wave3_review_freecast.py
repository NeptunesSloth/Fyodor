"""Wave 3 final review: mid-resolution free casts (608.2g) against save/load and a player leaving."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.storage.saves import load_payload
from tests import test_rules_refused_look as look
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_refused_look import OURS, build, choose, decision, put, stack_library, zone

cards = look.cards  # (the card pool fixture of those tests)


def build3(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, n) for n in OURS] + [(4, "Grizzly Bears"), (2, "Lightning Bolt"), (20, "Forest")])
    others = [deck(cards, "Atraxa, Praetors' Voice", [(1, "Divination"), (30, "Island")]) for _ in range(2)]
    setups = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=others[0]), PlayerSetup("Carol", cards=others[1])]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def _velomachus_attacks(s):
    velo = put(s, "Velomachus Lorehold", "battlefield")
    top = stack_library(s, ["Divination", "Lightning Bolt", "Grizzly Bears", "Forest", "Sign in Blood", "Collected Conjuring", "Forest"])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": velo.id, "target": "p2"}])
    pass_until_stack_empty(s)
    decision(s, "free_cast_pick")
    return velo, top


def test_a_free_cast_paused_on_its_target_survives_save_and_load(cards):
    s = build(cards)
    _, top = _velomachus_attacks(s)
    choose(s, [top[1]])  # Lightning Bolt, cast during the resolution: its target next
    decision(s, "cast_target")
    state, _ = load_payload({"state": s.state.model_dump(mode="json"), "history": s.history.to_dict()})
    again = GameSession(state, cards=cards)
    choose(again, ["p2"])
    assert set(zone(again.state, "p1", "library")[-6:]) == {top[0], top[2], top[3], top[4], top[5], top[6]}
    pass_until_stack_empty(again)
    assert again.state.cards[top[1]].zone == "p1:graveyard"
    assert again.state.rules.free_cast_then is None and again.state.rules.decision is None or \
        again.state.rules.decision.kind in ("declare_blockers", "confirm")


def test_the_caster_conceding_during_a_free_cast_leaves_nothing_pending(cards):
    s = build3(cards)
    _, top = _velomachus_attacks(s)
    choose(s, [top[1]])
    decision(s, "cast_target")
    act(s, "p1", type="concede")
    r = s.state.rules
    assert r.free_cast_then is None
    assert not [c for c in s.state.zones.get("stack", []) if s.state.cards[c].owner == "p1"]
    replay_matches(s)
