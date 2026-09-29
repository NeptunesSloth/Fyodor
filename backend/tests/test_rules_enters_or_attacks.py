""""Whenever ~ enters or attacks" (603.2: one ability, triggering on each of its events)."""

from __future__ import annotations

from tests.game_helpers import act
from tests.test_rules_attachments import build
from tests.test_rules_combat import attack, automate, creature
from tests.test_rules_effects import pass_until_stack_empty


def test_triggers_on_entering_and_on_attacking(cards):
    s = build(cards, "Test Herald")
    herald = next(c for c in s.state.cards.values() if c.name == "Test Herald")
    act(s, "p1", type="move", card_ids=[herald.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="cast_spell", card_id=herald.id)
    pass_until_stack_empty(s)
    assert s.state.cards[herald.id].zone == "p1:battlefield"
    assert s.state.players["p1"].life == 41  # it entered


def test_attacking_triggers_it_too(cards):
    from tests.test_rules_combat import table

    s = table(cards)
    creature(s, "p1", "Herald", "2/2", "Whenever this creature enters or attacks, you gain 1 life.")
    herald = next(c for c in s.state.cards.values() if c.name == "Herald")
    automate(s)
    life = s.state.players["p1"].life
    attack(s, (herald, "p2"))
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == life + 1
