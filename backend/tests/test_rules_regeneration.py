"""Regeneration (CR 701.19): shields replace destruction (lethal damage, destroy effects) this
turn; "can't be regenerated" ignores them; shields end at cleanup."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches, rules, token


def build(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Murder"), (1, "Wrath of God"), (1, "Day of Judgment"), (8, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Twisted Abomination"), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    act(s, "p1", type="draw", count=3)
    act(s, "p2", type="draw", count=1)
    ab = next(c for c in s.state.cards.values() if c.name == "Twisted Abomination")
    act(s, "p2", type="move", card_ids=[ab.id], to={"zone": "battlefield"})
    return s, ab


def cast(s, name, shields=0, **kw):
    """Alice casts ``name``; Bob answers with ``shields`` regeneration activations; all resolves."""
    card = next(s.state.cards[c] for c in zone(s.state, "p1", "hand") if s.state.cards[c].name == name)
    if shields:
        mana(s, "p2", B=shields)
    act(s, "p1", type="cast_spell", card_id=card.id, **kw)
    if shields:
        ab = next(c for c in s.state.cards.values() if c.name == "Twisted Abomination")
        if rules(s).priority == "p1":
            act(s, "p1", type="pass_priority")  # Bob gets priority with the spell on the stack
        assert rules(s).priority == "p2" and s.state.zones.get("stack")
        for _ in range(shields):
            act(s, "p2", type="activate_ability", card_id=ab.id, ability=0)  # "{B}: Regenerate Twisted Abomination."
    pass_until_stack_empty(s)


def test_shield_replaces_destroy(cards):
    s, ab = build(cards)
    mana(s, "p1", B=3)
    cast(s, "Murder", shields=1, targets=[ab.id])
    st = s.state
    assert st.cards[ab.id].zone == "p2:battlefield" and st.cards[ab.id].tapped  # regenerated: tapped
    assert not rules(s).regen_shields  # the shield is used up
    replay_matches(s)


def test_shield_replaces_lethal_damage_and_removes_damage(cards):
    s, ab = build(cards)
    mana(s, "p1", B=3)
    cast(s, "Murder", shields=2, targets=[ab.id])  # one shield is left over
    assert rules(s).regen_shields
    act(s, "p1", type="tap", card_ids=[ab.id], tapped=False)
    act(s, "p1", type="set_damage", card_ids=[ab.id], value=5)
    act(s, "p1", type="pass_priority")  # state-based actions
    st = s.state
    assert st.cards[ab.id].zone == "p2:battlefield" and st.cards[ab.id].damage == 0 and st.cards[ab.id].tapped


def test_cant_be_regenerated(cards):
    s, ab = build(cards)
    mana(s, "p1", W=2, C=2)
    cast(s, "Wrath of God", shields=1)  # "Destroy all creatures. They can't be regenerated."
    assert s.state.cards[ab.id].zone == "p2:graveyard"


def test_wrath_without_the_clause_is_regenerated_but_a_second_needs_a_second_shield(cards):
    s, ab = build(cards)
    token(s, "p1", "Squire")
    mana(s, "p1", W=2, C=2)
    cast(s, "Day of Judgment", shields=1)  # "Destroy all creatures."
    assert s.state.cards[ab.id].zone == "p2:battlefield"
    assert not any(c.name == "Squire" for c in s.state.cards.values())
    mana(s, "p1", B=3)
    cast(s, "Murder", targets=[ab.id])  # no shield left
    assert s.state.cards[ab.id].zone == "p2:graveyard"


def test_shields_end_at_cleanup(cards):
    s, ab = build(cards)
    mana(s, "p1", B=3)
    cast(s, "Murder", shields=2, targets=[ab.id])
    assert rules(s).regen_shields
    from tests.test_rules_effects import run_until

    run_until(s, lambda s: s.state.turn.active_player == "p2")
    assert not rules(s).regen_shields

