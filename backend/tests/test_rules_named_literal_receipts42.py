"""Literal named objects survive source-name changes (201.5)."""
from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_mana_followthrough_profiles import cards as followthrough_cards
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    yield from followthrough_cards.__wrapped__(settings)


@pytest.mark.parametrize('name', ['Approach of the Second Sun', 'Ebondeath, Dracolich', 'Relentless Rats', 'Brothers Yamazaki'])
def test_fresh_canonical_named_literal_cards_remain_full(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def sakashima(s, source):
    spell = put(s, 'Sakashima the Impostor', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'U': 2})
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    settle(s)
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        options = [o for o in d.options if o.card_id == source.id or o.id == source.id]
        assert options, d
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[options[0].id])
        settle(s)
    return spell


def test_sakashima_rats_count_literal_rats_not_its_own_new_name(cards):
    from app.rules.plan import Plan

    s = table(cards, ['Relentless Rats', 'Sakashima the Impostor'], [], [])
    to_phase(s, 'main1', 4)
    rat = put(s, 'Relentless Rats', 'battlefield')
    copy = sakashima(s, rat)
    original = Plan(s.state, 'p1', cards, None).ch(s.state.cards[rat.id])
    copied = Plan(s.state, 'p1', cards, None).ch(s.state.cards[copy.id])
    assert copied.name == 'Sakashima the Impostor' and copied.pt == (3, 3)
    assert original.pt == (2, 2)
    roundtrip(s)


def test_sakashima_brothers_legend_exception_counts_literal_brothers_not_renamed_copies(cards):
    s = table(cards, ['Brothers Yamazaki', 'Sakashima the Impostor', 'Cackling Counterpart'], [], [])
    to_phase(s, 'main1', 4)
    brother = put(s, 'Brothers Yamazaki', 'battlefield')
    copy = sakashima(s, brother)
    spell = put(s, 'Cackling Counterpart', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'U': 2})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[copy.id], sources=[])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'legend_rule'
    assert brother.id not in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[copy.id])
    answer(s)
    assert s.state.cards[brother.id].zone == s.state.cards[copy.id].zone == 'p1:battlefield'
    roundtrip(s)
