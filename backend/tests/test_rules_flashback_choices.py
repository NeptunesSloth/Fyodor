"""CR 118.9a, 702.34: choose the specific flashback alternative to pay."""
import pytest

from tests.test_rules_flashback_cost_modifiers import cards as _cards
from tests.test_rules_flashback_cost_modifiers import setup


@pytest.fixture()
def cards(settings):
    yield from _cards.__wrapped__(settings)


def granted(cards, name='Firebolt', stones=()):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put

    s, spell, _ = setup(cards, name=name, stone_owners=stones)
    mage = put(s, 'Snapcaster Mage', 'hand')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=mage.id)
    settle(s)
    wait_priority(s, 'p1')
    return s, spell


@pytest.mark.parametrize('choice,generic,stones', [(0, 4, ()), (1, 0, ()), (0, 2, ('p1',)), (1, 2, ('p2',))])
def test_choose_native_or_granted_with_modifiers_and_saved_prompt(cards, choice, generic, stones):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell = granted(cards, stones=stones)
    mana(s, C=generic, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p3'])
    d = s.state.rules.decision
    assert d.player == 'p1' and d.resume['step'] == 'flashback_choice'
    assert len([o for o in d.options if o.id != 'cancel']) == 2
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[str(choice)])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:exile'
    assert s.state.players['p3'].life == 38
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


def test_granted_deep_analysis_does_not_pay_native_life_cost(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell = granted(cards, name='Deep Analysis')
    mana(s, C=3, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p1'], flashback_choice=1)
    settle(s)
    assert s.state.players['p1'].life == 40
    assert s.state.cards[spell.id].zone == 'p1:exile'
    roundtrip(s)


def test_cancel_flashback_selection_does_not_spend_mana(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, spell = granted(cards)
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p3'])
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['cancel'])
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].mana['R'] == 1
    assert s.state.rules.decision is None
    roundtrip(s)


def test_castable_hint_accepts_cheaper_granted_flashback(cards):
    from app.rules.casting import castable
    from tests.test_rules_bandmate_references import mana

    s, spell = granted(cards)
    mana(s, R=1)
    assert castable(s.state, 'p1', spell, s.cards)


def test_native_deep_analysis_still_pays_life_when_granted_cost_exists(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell = granted(cards, name='Deep Analysis')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p1'], flashback_choice=0)
    settle(s)
    assert s.state.players['p1'].life == 37
    assert s.state.cards[spell.id].zone == 'p1:exile'
    roundtrip(s)
