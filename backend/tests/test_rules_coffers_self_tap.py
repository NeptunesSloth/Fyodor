"""-- playtest (nov 17) -- a mana ability with a mana cost (Cabal Coffers: "{2}, {T}: Add {B} for each Swamp you control") activated with
the pool short at a real table (players tap their own mana, payment "self"): like a spell (test_rules_self_tap.py), the "tap your mana"
prompt opens for its {2} (605.3a: mana abilities can be activated while paying it; the Coffers itself is not a source for its own cost),
and the ability resolves as soon as the pool covers it. Before, it was refused: "Add {2} to your mana pool first"."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable, mana_pool


def table(cards, swamps=3):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Cabal Coffers"), (swamps, "Swamp"), (5, "Island")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False))
    for prefs in state.rules.prefs.values():
        prefs.payment = "self"  # the table default
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    ids = [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name in ("Cabal Coffers", "Swamp")]
    act(s, "p1", type="move", card_ids=ids, to={"zone": "battlefield"})
    coffers = next(c for c in s.state.cards.values() if c.name == "Cabal Coffers")
    swamps_ = [c.id for c in s.state.cards.values() if c.name == "Swamp" and c.owner == "p1"]
    return s, coffers, swamps_


def test_coffers_asks_to_tap_for_its_cost_then_adds_its_mana(cards):
    s, coffers, swamps = table(cards)
    act(s, "p1", type="activate_ability", card_id=coffers.id, ability=0)
    d = s.state.rules.decision
    assert d is not None and d.display["kind"] == "tap_mana" and d.display["cost"] == "{2}"
    assert coffers.id not in d.display["sources"] and set(swamps) <= set(d.display["sources"])
    assert not coffers.tapped and mana_pool(s) == {}
    act(s, "p1", type="activate_ability", card_id=swamps[0], ability=0)
    assert s.state.rules.decision is not None
    act(s, "p1", type="activate_ability", card_id=swamps[1], ability=0)  # {2} paid: the Coffers taps and adds {B} per Swamp (three)
    assert s.state.rules.decision is None
    assert s.state.cards[coffers.id].tapped and mana_pool(s) == {"B": 3}


def test_coffers_with_the_pool_full_needs_no_prompt_and_cancel_leaves_it_untapped(cards):
    s, coffers, swamps = table(cards)
    act(s, "p1", type="activate_ability", card_id=coffers.id, ability=0)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["cancel"])
    assert s.state.rules.decision is None and not s.state.cards[coffers.id].tapped
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    act(s, "p1", type="activate_ability", card_id=coffers.id, ability=0)
    assert s.state.rules.decision is None and mana_pool(s) == {"B": 3}
