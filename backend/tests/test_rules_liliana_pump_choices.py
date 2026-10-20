"""Liliana's ±X nonmodal choice uses the native resolution-time Swamp count."""
from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from app.rules.sba import power, toughness
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle
from tests.test_rules_liliana_dark_realms import NAME
from tests.test_rules_liliana_dark_realms import cards as cards


def setup(cards, swamps=0, loyalty=3):
    from tests.test_rules_wave31d_spell_copies import hold

    s = build(cards, [NAME, *(['Swamp'] * 4), 'Forest', 'Urborg, Tomb of Yawgmoth', 'Grizzly Bears'], bob=[(1, 'Grizzly Bears'), (10, 'Island')])
    hold(s)
    source = put(s, NAME, 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=loyalty)
    lands = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Swamp']
    for land in lands[:swamps]:
        act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'battlefield'})
    target = put(s, 'Grizzly Bears', 'battlefield')
    return s, source, target, lands


def start(s, source, target):
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[target.id])


def choose(s, option):
    settle(s)
    d = s.state.rules.decision
    assert d and [o.label for o in d.options] == ['+X/+X', '-X/-X']
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[str(option)])
    settle(s)
    roundtrip(s)


def pt(s, cards, target):
    c = s.state.cards[target.id]
    ch = Plan(s.state, 'p1', cards, None).ch(c)
    return power(c, ch), toughness(c, ch)


def test_canonical_liliana_is_full_with_native_emblem_and_both_pump_choices(cards):
    c = coverage.of_card_data(cards.resolve(NAME))
    assert c.level == 'FULL', c.manual_parts


@pytest.mark.parametrize('option,expected', [(0, (3, 3)), (1, (1, 1))])
def test_both_signed_choices_use_count_and_expire_at_end_of_turn(cards, option, expected):
    from tests.test_rules_wave34b_activated import to_phase

    s, source, target, _ = setup(cards, swamps=1)
    start(s, source, target)
    assert s.state.cards[source.id].zone == 'p1:graveyard'  # Paying -3 does not stop its pending ability.
    choose(s, option)
    assert pt(s, cards, target) == expected
    to_phase(s, 'main1', turn=s.state.turn.number + 1)
    assert pt(s, cards, target) == (2, 2)
    roundtrip(s)


def test_swamps_are_counted_when_ability_resolves_not_when_activated(cards):
    s, source, target, lands = setup(cards, swamps=1)
    start(s, source, target)
    act(s, 'p1', type='move', card_ids=[lands[1].id], to={'player': 'p1', 'zone': 'battlefield'})
    choose(s, 0)
    assert pt(s, cards, target) == (4, 4)


def test_zero_swamps_still_offers_the_choice_and_changes_neither_stat(cards):
    s, source, target, _ = setup(cards)
    start(s, source, target)
    choose(s, 1)
    assert pt(s, cards, target) == (2, 2)


def test_minus_choice_can_kill_target_by_zero_toughness(cards):
    s, source, target, _ = setup(cards, swamps=2)
    start(s, source, target)
    choose(s, 1)
    assert s.state.cards[target.id].zone == 'p1:graveyard'


def test_pending_ability_uses_original_controller_after_source_control_changes(cards):
    s, source, target, _ = setup(cards, swamps=1, loyalty=4)
    start(s, source, target)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    choose(s, 0)
    assert pt(s, cards, target) == (3, 3)


def test_urborg_current_types_count_as_swamps_at_resolution(cards):
    s, source, target, _ = setup(cards, swamps=1)
    put(s, 'Forest', 'battlefield')
    start(s, source, target)
    put(s, 'Urborg, Tomb of Yawgmoth', 'battlefield')
    choose(s, 0)
    assert pt(s, cards, target) == (5, 5)  # Swamp + Forest + Urborg.


def test_blinked_target_is_illegal_and_no_resolution_choice_is_asked(cards):
    s, source, target, _ = setup(cards, swamps=1)
    start(s, source, target)
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    assert s.state.rules.decision is None and pt(s, cards, target) == (2, 2)
    roundtrip(s)
