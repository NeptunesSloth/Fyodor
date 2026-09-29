"""The shared resolution / trigger context contract (app/rules/context.py): explicit bindings to
objects, players, amounts and payments, following 400.7 (new objects), 400.7j (an effect finds what
it moved to a public zone), 608.2h (last known information), 108.4a (owner for cards off the
battlefield and stack)."""

from __future__ import annotations

import json

from app.rules import context
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_attachments import build, token


def plan_of(s, cards):
    return Plan(s.state, "p1", cards, None)


def test_bound_object_moved_to_a_public_zone_is_the_new_object(cards):
    s = build(cards)
    ogre = token(s, "p2", "Ogre", "2/2")
    act(s, "p2", type="counter", card_ids=[ogre.id], kind="+1/+1", delta=2)
    plan = plan_of(s, cards)
    ctx: dict = {"controller": "p1"}
    context.bind_objects(plan, ctx, "e0", [ogre.id])
    before = [context.ref_of(plan, ogre.id)]
    plan.do({"type": "move", "card_ids": [ogre.id], "to": {"zone": "exile"}})  # (a token: it ceases to exist)
    context.bind_moved(plan, ctx, "e1", [b for b in before if b is not None])
    assert context.objects(plan, ctx, "e0") == []  # the creature is gone (400.7)
    card, ch = context.info(plan, ctx, "e0")  # but its last known information remains (608.2h)
    assert ch.pt == (4, 4)
    assert context.players(plan, ctx, "e0.controller") == ["p2"]
    json.dumps(ctx)  # (JSON-native: survives pauses, saves and replay)


def test_moved_card_found_in_the_new_zone_then_lost_after_another_move(cards):
    s = build(cards)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    plan = plan_of(s, cards)
    ctx: dict = {"controller": "p1"}
    before = [context.ref_of(plan, forest.id)]
    plan.do({"type": "move", "card_ids": [forest.id], "to": {"zone": "exile"}})
    context.bind_moved(plan, ctx, "exiled", [b for b in before if b is not None])
    assert context.objects(plan, ctx, "exiled") == [forest.id]  # 400.7j: this effect finds it in exile
    assert context.players(plan, ctx, "exiled.controller") == ["p1"]  # (off the battlefield: its owner, 108.4a)
    plan.do({"type": "move", "card_ids": [forest.id], "to": {"zone": "graveyard"}})
    assert context.objects(plan, ctx, "exiled") == []  # a new object again (400.7)


def test_moved_into_a_hidden_zone_keeps_only_what_it_was(cards):
    s = build(cards)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    plan = plan_of(s, cards)
    ctx: dict = {"controller": "p1"}
    before = [context.ref_of(plan, forest.id)]
    plan.do({"type": "move", "card_ids": [forest.id], "to": {"zone": "hand"}})
    context.bind_moved(plan, ctx, "e0", [b for b in before if b is not None])
    assert context.objects(plan, ctx, "e0") == []  # 608.2h: moved to a hidden zone: last known information only
    assert context.info(plan, ctx, "e0") is not None


def test_players_amounts_and_payments(cards):
    s = build(cards)
    plan = plan_of(s, cards)
    ctx: dict = {"controller": "p1", "event": {"kind": "draw", "players": ["p2"], "amount": 3, "objects": []}}
    context.bind_players(ctx, "that", ["p2", "p9"])
    context.bind_amount(ctx, "dealt", 4)
    context.bind_payment(ctx, "pay0", False)
    assert context.players(plan, ctx, "that") == ["p2"]  # (a player not in the game is skipped, 800.4a)
    assert context.players(plan, ctx, "event") == ["p2"] and context.amount(ctx, "event") == 3
    assert context.amount(ctx, "dealt") == 4
    assert not context.succeeded(ctx, "pay0") and not context.succeeded(ctx, "missing")
    context.bind_payment(ctx, "pay0", True)
    assert context.succeeded(ctx, "pay0")
    json.dumps(ctx)
