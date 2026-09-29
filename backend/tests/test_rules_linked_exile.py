"""610.3c: "exile target … until ~ leaves the battlefield" — they return when it leaves."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana
from tests.test_rules_suspend import until


def test_banisher_priest(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Banisher Priest"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Grizzly Bears"), (9, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "battlefield"})
    s = GameSession(enable(s.state), cards=cards)
    act(s, "p1", type="pass_priority")
    priest = next(c for c in s.state.cards.values() if c.name == "Banisher Priest")
    act(s, "p1", type="move", card_ids=[priest.id], to={"zone": "hand"})
    mana(s, W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=priest.id)
    until(s, lambda s: s.state.rules.decision is not None or s.state.cards[bears.id].zone == "p2:exile")
    d = s.state.rules.decision
    if d is not None:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[bears.id].zone == "p2:exile"
    act(s, "p1", type="set_damage", card_ids=[priest.id], value=2)
    act(s, "p1", type="pass_priority")  # the Priest dies → the Bears come back
    until(s, lambda s: s.state.cards[bears.id].zone == "p2:battlefield", limit=20)
    assert s.state.cards[priest.id].zone == "p1:graveyard"



def test_fabricate(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(2, "Glint-Sleeve Artisan"), (8, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    first, second = [c for c in s.state.cards.values() if c.name == "Glint-Sleeve Artisan"]
    act(s, "p1", type="move", card_ids=[first.id, second.id], to={"zone": "hand"})
    for card, answer in ((first, "counters"), (second, "servos")):
        mana(s, W=1, C=2)
        act(s, "p1", type="cast_spell", card_id=card.id)
        until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.prompt == "Fabricate 1")
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[answer])
        until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[first.id].counters == {"+1/+1": 1} and not s.state.cards[second.id].counters
    assert sum(1 for c in s.state.cards.values() if c.name == "Servo") == 1
