"""A Spirit Guide's mana ability, activated from the hand (113.6m, 605.3a), obeys the effects that prohibit activations (602.5):
with priority and while paying for a spell. Phyrexian Revoker stops mana abilities too; Pithing Needle ("unless they're mana
abilities") and split second (702.61b) don't. Real Oracle text; every scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, to_hand

EXTRA = [
    real("Simian Spirit Guide", "{2}{R}", 3, "Creature — Ape Spirit", "Exile this card from your hand: Add {R}.", ("2", "2"), "R"),
    real("Phyrexian Revoker", "{2}", 2, "Artifact Creature — Phyrexian Horror",
         "As this creature enters, choose a nonland card name.\nActivated abilities of sources with the chosen name can't be activated.", ("2", "1")),
    real("Pithing Needle", "{1}", 1, "Artifact",
         "As this artifact enters, choose a card name.\nActivated abilities of sources with the chosen name can't be activated unless they're mana abilities."),
    real("Rite of Flame", "{R}", 1, "Sorcery", "Add {R}{R}, then add {R} for each card named Rite of Flame in each graveyard.", None, "R"),
    real("Sudden Shock", "{1}{R}", 2, "Instant",
         "Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.)\n"
         "Sudden Shock deals 2 damage to any target.", None, "R"),
]
GUIDE = "Simian Spirit Guide"


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def naming_guide(cards, limiter):
    """Alice's ``limiter`` is on the battlefield naming Simian Spirit Guide (201.4, 709.4a); the Guide is in her hand."""
    s = build(cards, [GUIDE, limiter, "Rite of Flame"])
    act(s, "p1", type="add_mana", player="p1", mana={"W": 2})
    act(s, "p1", type="cast_spell", card_id=to_hand(s, limiter).id)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.options[0].id == "__name__"
    act(s, "p1", type="choose", decision_id=d.id, name=GUIDE)
    assert card_named(s, limiter).zone == "p1:battlefield"
    return s, to_hand(s, GUIDE)


def paying_for_rite(s):
    """Alice casts Rite of Flame ({R}) and pays by hand: the payment prompt is open (601.2g-h)."""
    act(s, "p1", type="set_prefs", payment="self")
    rite = to_hand(s, "Rite of Flame")
    act(s, "p1", type="cast_spell", card_id=rite.id)
    d = s.state.rules.decision
    assert d is not None and (d.resume or {}).get("step") == "pay_mana"
    return rite


def test_revoker_stops_a_spirit_guide_with_priority(cards):
    s, guide = naming_guide(cards, "Phyrexian Revoker")
    with pytest.raises(ActionError, match="can't be activated"):
        act(s, "p1", type="activate_ability", card_id=guide.id, ability=0)
    assert s.state.cards[guide.id].zone == "p1:hand"
    check(s)


def test_revoker_stops_a_spirit_guide_while_paying(cards):
    """602.5: the prohibition holds during a payment too (605.3a only says when a mana ability may be activated)."""
    s, guide = naming_guide(cards, "Phyrexian Revoker")
    rite = paying_for_rite(s)
    with pytest.raises(ActionError, match="can't be activated"):
        act(s, "p1", type="activate_ability", card_id=guide.id, ability=0)
    assert s.state.cards[guide.id].zone == "p1:hand"
    assert (s.state.rules.decision.resume or {}).get("step") == "pay_mana"  # the payment is still open
    assert s.state.cards[rite.id].zone != "p1:graveyard"
    check(s)


def test_pithing_needle_lets_a_spirit_guide_add_mana_with_priority(cards):
    """605.1a: the Guide's ability is a mana ability, which Pithing Needle leaves alone."""
    s, guide = naming_guide(cards, "Pithing Needle")
    act(s, "p1", type="activate_ability", card_id=guide.id, ability=0)
    assert s.state.cards[guide.id].zone == "p1:exile" and mana_pool(s).get("R") == 1
    check(s)


def test_pithing_needle_lets_a_spirit_guide_pay_for_a_spell(cards):
    s, guide = naming_guide(cards, "Pithing Needle")
    rite = paying_for_rite(s)
    act(s, "p1", type="activate_ability", card_id=guide.id, ability=0)
    assert s.state.cards[guide.id].zone == "p1:exile"
    assert s.state.cards[rite.id].zone != "p1:hand"  # paid: cast
    check(s)


def test_a_spirit_guide_adds_mana_while_a_split_second_spell_is_on_the_stack(cards):
    """702.61b: players may activate mana abilities while a spell with split second is on the stack."""
    s = build(cards, [GUIDE, "Sudden Shock"])
    guide = to_hand(s, GUIDE)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="add_mana", player="p1", mana={"R": 2})
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Sudden Shock").id, targets=["p2"])
    assert s.state.zones.get("stack") and s.state.rules.priority == "p1"
    act(s, "p1", type="activate_ability", card_id=guide.id, ability=0)
    assert s.state.cards[guide.id].zone == "p1:exile" and mana_pool(s).get("R") == 1
    check(s)
