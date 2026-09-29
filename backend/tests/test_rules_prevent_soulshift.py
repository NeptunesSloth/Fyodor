"""Prevention shields (615.7) and soulshift (702.46: a dies trigger targeting a graveyard card)."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_suspend import until


def test_prevent_noncombat_damage(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Lightning Bolt"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    medic = creature(s, "p1", "Medic", "1/1", "{1}: Prevent the next 1 damage that would be dealt to any target this turn.")
    ogre = creature(s, "p2", "Ogre", "3/4")
    s = GameSession(enable(s.state), cards=cards)
    act(s, "p1", type="pass_priority")
    bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand"})
    mana(s, C=2)
    for _ in range(2):
        act(s, "p1", type="activate_ability", card_id=medic.id, ability=0, targets=[ogre.id])
        pass_until_stack_empty(s)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[ogre.id])
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].damage == 1  # 3 − 2 prevented


def test_prevent_combat_damage_to_a_player(cards):
    s = table(cards)
    brute = creature(s, "p1", "Brute", "4/4")
    medic = creature(s, "p2", "Medic", "0/1", "{1}: Prevent the next 1 damage that would be dealt to any target this turn.")
    automate(s)
    s.state.rules.prevention["p2"] = 3  # (three shields from the Medic)
    attack(s, (brute, "p2"))
    until(s, lambda s: s.state.players["p2"].life < 40 or s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 39 and not s.state.rules.prevention
    assert medic.id in s.state.cards


def test_soulshift_returns_a_spirit(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Hundred-Talon Kami"), (1, "Kami of Ancient Law"), (8, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    big = next(c for c in s.state.cards.values() if c.name == "Hundred-Talon Kami")
    small = next(c for c in s.state.cards.values() if c.name == "Kami of Ancient Law")
    act(s, "p1", type="move", card_ids=[big.id], to={"zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[small.id], to={"zone": "graveyard"})
    s = GameSession(enable(s.state), cards=cards)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="set_damage", card_ids=[big.id], value=3)
    act(s, "p1", type="pass_priority")  # dies → soulshift
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert small.id in {o.id for o in d.options} and big.id not in {o.id for o in d.options}  # MV 4 or less
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[small.id])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "confirm")
    d = s.state.rules.decision  # "you may"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    pass_until_stack_empty(s)
    assert s.state.cards[small.id].zone == "p1:hand"
    assert zone(s.state, "p1", "graveyard") == [big.id]
