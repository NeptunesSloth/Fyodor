"""Shock lands, explore, investigate, and "When ~ becomes the target …, sacrifice it"."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import effects
from app.rules.plan import Plan
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_effects import mana
from tests.test_rules_suspend import until


def build(cards, names):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def named(s, name):
    return next(c for c in s.state.cards.values() if c.name == name)


def test_shock_land_pay_or_tapped(cards):
    s = build(cards, ["Breeding Pool"])
    pool = named(s, "Breeding Pool")
    act(s, "p1", type="move", card_ids=[pool.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=pool.id)
    d = s.state.rules.decision
    assert d.resume["step"] == "shock" and s.state.cards[pool.id].zone == "p1:hand"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    assert s.state.cards[pool.id].zone == "p1:battlefield" and not s.state.cards[pool.id].tapped
    assert s.state.players["p1"].life == 38


def test_shock_land_enters_tapped(cards):
    s = build(cards, ["Breeding Pool"])
    pool = named(s, "Breeding Pool")
    act(s, "p1", type="move", card_ids=[pool.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=pool.id, pay_life=False)
    assert s.state.cards[pool.id].tapped and s.state.players["p1"].life == 40


def test_becomes_target_sacrifice(cards):
    s = build(cards, ["Lightning Bolt"])
    act(s, "p2", type="create_token", player="p2", token={
        "name": "Phantom", "type_line": "Token Creature — Illusion", "power": "2", "toughness": "2",
        "text": "When this creature becomes the target of a spell or ability, sacrifice it."})
    phantom = named(s, "Phantom")
    bolt = named(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand"})
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[phantom.id])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert phantom.id not in s.state.cards or s.state.cards[phantom.id].zone == "p2:graveyard"


def test_investigate_and_explore_parse():
    from app.rules.scripts import parse_effects

    assert parse_effects("Investigate.")[0][0]["token"]["name"] == "Clue"
    assert parse_effects("It explores.")[0] == [{"do": "explore"}]


def test_explore(cards):
    s = build(cards, ["Lightning Bolt"])
    act(s, "p1", type="create_token", player="p1", token={"name": "Scout", "type_line": "Token Creature — Merfolk",
                                                         "power": "1", "toughness": "1"})
    scout = named(s, "Scout")
    plan = Plan(s.state, "p1", cards, None)
    ctx = {"controller": "p1", "source_card": scout.id, "source_object": plan.oid(scout.id), "targets": [], "effects": []}
    hand = len(zone(plan.state, "p1", "hand"))
    top = zone(plan.state, "p1", "library")[0]
    land_on_top = plan.state.cards[top].name == "Forest"
    done = effects.explore(plan, ctx, {"do": "explore"})
    if land_on_top:  # a land: into your hand, no counter
        assert done and len(zone(plan.state, "p1", "hand")) == hand + 1 and not plan.state.cards[scout.id].counters
    else:  # a nonland card: a +1/+1 counter, then you choose where it goes
        assert not done and plan.state.cards[scout.id].counters == {"+1/+1": 1}
        assert plan.rules.decision.resume["step"] == "explore"
