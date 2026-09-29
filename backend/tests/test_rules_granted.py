"""Statics that grant quoted abilities: "All Slivers have "…"", "Lands you control have "…"",
"Commander creatures you own have "…"" (layer 6)."""

from __future__ import annotations

from app.rules.casting import activatable
from app.rules.plan import Plan
from app.rules.view import rules_view
from tests.game_helpers import act, turn_on, zone
from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_effects import pass_until_stack_empty, run_until


def token(s, pid, name, type_line, text="", pt=("1", "1")):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": pt[0],
                                                        "toughness": pt[1], "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def test_all_slivers_share_a_granted_activated_ability(cards):
    s = table(cards)
    token(s, "p1", "Clot", "Token Creature — Sliver", 'All Slivers have "{2}: Regenerate this permanent."')
    theirs = token(s, "p2", "Wing", "Token Creature — Sliver")
    turn_on(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="pass_priority")
    ch = Plan(s.state, "p2", cards, None).ch(s.state.cards[theirs.id])
    assert any(a.index == 100 and "Regenerate" in a.text for a in ch.abilities)
    assert rules_view(s.state, "p1", cards)["stats"][theirs.id]["abilities"][0]["index"] == 100


def test_lands_you_control_have_a_mana_ability(cards):
    s = table(cards)
    token(s, "p1", "Lantern", "Token Artifact — Test", 'Lands you control have "{T}: Add one mana of any color."', (None, None))
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    turn_on(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=100, mana_choice="R")
    assert s.state.players["p1"].mana == {"R": 1}


def test_commander_creatures_you_own_get_the_trigger(cards):
    s = table(cards)
    token(s, "p1", "Heritage", "Token Enchantment — Test", 'Commander creatures you own have "Whenever this creature attacks, draw a card."', (None, None))
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    goblin = creature(s, "p1", "Grunt", "1/1")
    automate(s)
    before = len(zone(s.state, "p1", "hand"))
    attack(s, (krenko, "p2"), (goblin, "p2"))
    pass_until_stack_empty(s)
    run_until(s, lambda s: len(zone(s.state, "p1", "hand")) > before)
    assert len(zone(s.state, "p1", "hand")) == before + 1  # only the commander draws
    assert {"card_id": goblin.id, "ability": 100} not in activatable(s.state, "p1", cards)
