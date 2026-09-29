"""Modal spells (CR 700.2): modes are chosen as the spell is cast (601.2b, 700.2a), then a target
for each chosen mode that needs one (601.2c, 700.2c/f); on resolution each mode's target is
checked on its own, and the spell does nothing only if all its targets are illegal (608.2b)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.characteristics import printed_from_data
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty


def respond_on(s):
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"


def test_modes_are_asked_then_each_modes_target(cards):
    s = build(cards, "Test Duo")
    ogre = token(s, "p2", "Ogre", "5/5")
    duo = to_hand(s, "Test Duo")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=duo.id)
    d = s.state.rules.decision
    assert d.resume["step"] == "cast_modes" and (d.min_choices, d.max_choices) == (2, 2)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["0:0", "1:0"])  # 2 damage and 3 damage
    d = s.state.rules.decision
    assert d.resume["step"] == "cast_slot_target"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[ogre.id])  # mode 1: the Ogre
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[ogre.id])  # mode 2: the same Ogre (601.2c)
    pass_until_stack_empty(s)
    assert ogre.id not in s.state.cards  # 2 + 3 damage: the 5/5 token died


def test_modes_and_targets_given_up_front(cards):
    s = build(cards, "Test Duo")
    hand = len(zone(s.state, "p1", "hand"))
    duo = to_hand(s, "Test Duo")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=duo.id, modes=[1, 2], targets=["p2"])  # 3 to Bob, draw
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37 and len(zone(s.state, "p1", "hand")) == hand + 1


def test_wrong_number_of_modes_or_repeats_are_refused(cards):
    s = build(cards, "Test Duo")
    duo = to_hand(s, "Test Duo")
    mana(s, R=1)
    with pytest.raises(ActionError, match="Choose 2"):
        act(s, "p1", type="cast_spell", card_id=duo.id, modes=[2])
    with pytest.raises(ActionError, match="same mode"):
        act(s, "p1", type="cast_spell", card_id=duo.id, modes=[2, 2])


def test_a_mode_without_a_legal_target_cant_be_chosen(cards):
    """700.2a: no artifact on the battlefield: "Destroy target artifact" can't be chosen."""
    s = build(cards, "Test Shatter Charm")
    charm = to_hand(s, "Test Shatter Charm")
    mana(s, R=1)
    with pytest.raises(ActionError, match="no legal target"):
        act(s, "p1", type="cast_spell", card_id=charm.id, modes=[0])
    act(s, "p1", type="cast_spell", card_id=charm.id)
    d = s.state.rules.decision
    assert [o.id for o in d.options] == ["1:0"]  # only "Draw a card." is offered


def test_one_illegal_target_the_other_mode_still_happens(cards):
    s = build(cards, "Test Duo")
    respond_on(s)
    ogre = token(s, "p2", "Ogre", "5/5")
    duo = to_hand(s, "Test Duo")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=duo.id, modes=[0, 1], targets=[ogre.id, "p2"])
    act(s, "p2", type="move", card_ids=[ogre.id], to={"zone": "graveyard"})  # the Ogre is gone
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37  # the 3 damage to Bob still happened
    assert s.state.cards[duo.id].zone == "p1:graveyard"


def test_all_targets_illegal_it_does_nothing(cards):
    s = build(cards, "Test Duo")
    respond_on(s)
    ogre = token(s, "p2", "Ogre", "5/5")
    duo = to_hand(s, "Test Duo")
    hand = len(zone(s.state, "p1", "hand"))
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=duo.id, modes=[0, 2], targets=[ogre.id])
    act(s, "p2", type="move", card_ids=[ogre.id], to={"zone": "graveyard"})
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hand - 1  # no card drawn (it didn't resolve)


def test_commander_lets_you_choose_both(cards):
    s = build(cards, "Test Commander Choice")
    spell = to_hand(s, "Test Commander Choice")
    mana(s, G=1)
    with pytest.raises(ActionError, match="Choose 1"):
        act(s, "p1", type="cast_spell", card_id=spell.id, modes=[0, 1])
    krenko = named(s, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})  # you control a commander
    act(s, "p1", type="cast_spell", card_id=spell.id, modes=[0, 1])
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 42


def test_same_mode_more_than_once(cards):
    s = build(cards, "Test Triple")
    spell = to_hand(s, "Test Triple")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, modes=[0, 0, 0])  # 700.2d
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 43


def test_modal_spells_are_full(cards):
    for name in ("Test Duo", "Test Commander Choice", "Test Triple", "Test Shatter Charm"):
        data = cards.get(cards.resolve(name)["id"])
        assert coverage.of_characteristics(printed_from_data(data)).level == "FULL", name
