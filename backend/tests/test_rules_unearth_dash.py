"""Unearth (702.84) and dash (702.109): haste, a delayed "next end step" trigger, and unearth's
"exile it instead if it would leave the battlefield" replacement."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_suspend import until


def build(cards, name, zone):
    alice = deck(cards, "Krenko, Mob Boss", [(1, name), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    card = next(c for c in s.state.cards.values() if c.name == name)
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": zone})
    return s, card


def haste(s, cards, card):
    return "haste" in Plan(s.state, "p1", cards, None).ch(s.state.cards[card.id]).keywords


def test_unearth_returns_with_haste_then_is_exiled_at_end_step(cards):
    s, zombie = build(cards, "Dregscape Zombie", "graveyard")
    mana(s, B=1)
    act(s, "p1", type="activate_ability", card_id=zombie.id, ability=0)
    pass_until_stack_empty(s)
    assert s.state.cards[zombie.id].zone == "p1:battlefield" and haste(s, cards, zombie)
    until(s, lambda s: s.state.cards[zombie.id].zone != "p1:battlefield")
    assert s.state.cards[zombie.id].zone == "p1:exile"


def test_unearthed_creature_that_dies_is_exiled_instead(cards):
    s, zombie = build(cards, "Dregscape Zombie", "graveyard")
    mana(s, B=1)
    act(s, "p1", type="activate_ability", card_id=zombie.id, ability=0)
    pass_until_stack_empty(s)
    act(s, "p1", type="set_damage", card_ids=[zombie.id], value=1)
    act(s, "p1", type="pass_priority")  # state-based actions: lethal damage
    assert s.state.cards[zombie.id].zone == "p1:exile"


def test_dash_haste_and_back_to_hand(cards):
    s, scout = build(cards, "Mardu Scout", "hand")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=scout.id, dash=True)
    pass_until_stack_empty(s)
    assert s.state.cards[scout.id].zone == "p1:battlefield" and haste(s, cards, scout)
    until(s, lambda s: s.state.cards[scout.id].zone != "p1:battlefield")
    assert s.state.cards[scout.id].zone == "p1:hand"


def test_buyback_returns_the_spell_to_hand(cards):
    s, capsize = build(cards, "Capsize", "hand")
    creature_ = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[creature_.id], to={"zone": "battlefield"})
    mana(s, U=2, C=4)
    act(s, "p1", type="cast_spell", card_id=capsize.id, buyback=True, targets=[creature_.id])
    pass_until_stack_empty(s)
    assert s.state.cards[capsize.id].zone == "p1:hand" and s.state.cards[creature_.id].zone == "p1:hand"
    assert s.state.players["p1"].mana == {}  # {1}{U}{U} + {3}
    act(s, "p1", type="move", card_ids=[creature_.id], to={"zone": "battlefield"})
    mana(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=capsize.id, targets=[creature_.id])
    pass_until_stack_empty(s)
    assert s.state.cards[capsize.id].zone == "p1:graveyard"


def _looter_table(cards):
    from tests.test_rules_combat import turn_on

    alice = deck(cards, "Krenko, Mob Boss", [(1, "Merfolk Looter"), (1, "Fiery Temper"), (8, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    looter = next(c for c in s.state.cards.values() if c.name == "Merfolk Looter")
    temper = next(c for c in s.state.cards.values() if c.name == "Fiery Temper")
    act(s, "p1", type="move", card_ids=[looter.id], to={"zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[temper.id], to={"zone": "hand"})
    turn_on(s)
    act(s, "p1", type="pass_priority")
    return s, looter, temper


def _loot_away_temper(s, looter, temper):
    act(s, "p1", type="activate_ability", card_id=looter.id, ability=0)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_cards")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[temper.id])
    until(s, lambda s: s.state.rules.decision is not None and "Madness" in s.state.rules.decision.prompt)
    assert s.state.cards[temper.id].zone == "p1:exile"
    return s.state.rules.decision


def test_madness_cast_for_its_madness_cost(cards):
    s, looter, temper = _looter_table(cards)
    d = _loot_away_temper(s, looter, temper)
    mana(s, R=1)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.players["p2"].life == 37 and s.state.cards[temper.id].zone == "p1:graveyard"
    assert s.state.players["p1"].mana == {}


def test_madness_declined_goes_to_graveyard(cards):
    s, looter, temper = _looter_table(cards)
    d = _loot_away_temper(s, looter, temper)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    assert s.state.cards[temper.id].zone == "p1:graveyard" and not s.state.rules.free_casts
