"""CR 602.2b, 700.2: activated modal abilities may choose a target group before paying."""
import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_ordered_graveyard_library import cards as _cards
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    yield from _cards.__wrapped__(settings)


def setup(cards):
    s = table(cards, ['Bow of Nylea', 'Perilous Myr', 'Lightning Bolt', 'Misinformation'], ['Perilous Myr', 'Lightning Bolt', 'Mocking Sprite'])
    bow = put(s, 'Bow of Nylea', 'battlefield')
    selected = [put(s, name, 'graveyard') for name in ['Perilous Myr', 'Lightning Bolt', 'Forest', 'Misinformation']]
    mana(s, C=1, G=1)
    return s, bow, selected


def activate(s, bow, selected, *, mode=3):
    act(s, 'p1', type='activate_ability', card_id=bow.id, ability=1, modes=[mode],
        targets=[c.id for c in selected], target_counts=[len(selected)] if mode == 3 else [])


def test_bow_all_modes_are_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve('Bow of Nylea')).level == 'FULL'


def test_group_targets_and_private_bottom_order_are_saved(cards):
    s, bow, selected = setup(cards)
    activate(s, bow, selected)
    entry = next(iter(s.state.rules.stack.values()))
    assert len(entry.groups[0]) == 4 and entry.group_specs[0]['min'] == 0 and entry.group_specs[0]['max'] == 4
    assert not entry.slots
    assert s.state.cards[bow.id].tapped and not any(s.state.players['p1'].mana.values())
    d = until_asked(s)
    assert d.kind == 'order' and d.player == 'p1'
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    roundtrip(s)
    order = [c.id for c in reversed(selected)]
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=order)
    settle(s)
    assert s.state.zones['p1:library'][-4:] == list(reversed(order))
    roundtrip(s)


@pytest.mark.parametrize('number', [0, 1])
def test_group_zero_or_one_target_needs_no_order_decision(cards, number):
    s, bow, selected = setup(cards)
    activate(s, bow, selected[:number])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[bow.id].tapped and not any(s.state.players['p1'].mana.values())
    if number:
        assert s.state.zones['p1:library'][-1] == selected[0].id
    roundtrip(s)


def test_group_prompt_precedes_payment_and_can_choose_zero(cards):
    s, bow, _ = setup(cards)
    act(s, 'p1', type='activate_ability', card_id=bow.id, ability=1, modes=[3])
    d = s.state.rules.decision
    assert d.kind == 'choose_cards' and d.min_choices == 0 and d.max_choices == 4
    assert not s.state.cards[bow.id].tapped and s.state.players['p1'].mana == {'C': 1, 'G': 1}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.cards[bow.id].tapped and not any(s.state.players['p1'].mana.values())
    roundtrip(s)


def test_cancelling_group_prompt_spends_nothing(cards):
    s, bow, _ = setup(cards)
    act(s, 'p1', type='activate_ability', card_id=bow.id, ability=1, modes=[3])
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['cancel'])
    assert s.state.rules.decision is None and not s.state.rules.stack
    assert not s.state.cards[bow.id].tapped and s.state.players['p1'].mana == {'C': 1, 'G': 1}
    roundtrip(s)


def test_group_rejects_opponents_graveyard_before_payment(cards):
    s, bow, _ = setup(cards)
    theirs = put(s, 'Perilous Myr', 'graveyard', 'p2')
    with pytest.raises(ActionError):
        activate(s, bow, [theirs])
    assert not s.state.cards[bow.id].tapped and s.state.players['p1'].mana == {'C': 1, 'G': 1}
    roundtrip(s)


def test_group_rechecks_targets_and_only_orders_remaining_legal_cards(cards):
    s, bow, selected = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    activate(s, bow, selected[:3])
    act(s, 'p1', type='move', card_ids=[selected[0].id], to={'player': 'p1', 'zone': 'hand'})
    d = until_asked(s)
    assert d.kind == 'order' and {o.id for o in d.options} == {selected[1].id, selected[2].id}
    order = [selected[2].id, selected[1].id]
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=order)
    settle(s)
    assert s.state.zones['p1:library'][-2:] == list(reversed(order))
    assert s.state.cards[selected[0].id].zone == 'p1:hand'
    roundtrip(s)


def test_other_bow_modes_keep_single_target_slot_and_untargeted_effect(cards):
    from tests.test_rules_conditionals import settle as finish

    s, bow, _ = setup(cards)
    target = put(s, 'Perilous Myr', 'battlefield')
    activate(s, bow, [target], mode=0)
    entry = next(iter(s.state.rules.stack.values()))
    assert len(entry.slots) == 1 and not entry.groups
    finish(s)
    assert s.state.cards[target.id].counters['+1/+1'] == 1
    act(s, 'p1', type='tap', card_ids=[bow.id], tapped=False)
    mana(s, C=1, G=1)
    activate(s, bow, [], mode=2)
    finish(s)
    assert s.state.players['p1'].life == 43
    act(s, 'p1', type='tap', card_ids=[bow.id], tapped=False)
    mana(s, C=1, G=1)
    flyer = put(s, 'Mocking Sprite', 'battlefield', 'p2')
    activate(s, bow, [flyer], mode=1)
    finish(s)
    assert s.state.cards[flyer.id].zone == 'p2:graveyard'
    roundtrip(s)
