"""Shared helpers of the wave 9C scenario tests (a table with Alice and Bob, rules automation on)."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import sba
from app.rules.plan import Plan
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle
from tests.test_rules_effects import replay_matches


def reloaded(s):
    """The table as a fresh session rebuilt from the saved history (a save and a load)."""
    return GameSession(s.history.rebuild(), cards=s.cards)


def build(cards, mine=(), theirs=(), forests=9, islands=10):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (forests, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (islands, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def card_named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def to_hand(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def put(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    settle(s)


def zone_of(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone


def pt(s, name, pid="p1"):
    c = s.state.cards[card_named(s, name, pid).id]
    ch = Plan(s.state, "p1", s.cards, None).ch(c)
    return sba.power(c, ch), sba.toughness(c, ch)


def life(s, pid="p1"):
    return s.state.players[pid].life


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))
