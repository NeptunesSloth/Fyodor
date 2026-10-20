"""CR 603.2c/611.2c: fifth-draw trigger and one self/group pump batch."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle

DATA = Path(__file__).parent / 'fixtures/alandra_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='ala', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAME = 'Alandra, Sky Dreamer'


def setup(cards):
    from tests.test_rules_wave31d_spell_copies import hold

    s = build(cards, [NAME, 'Wind Drake', 'Maskwood Nexus', 'Grizzly Bears', *(['Reach Through Mists'] * 6), 'Ancestral Recall', 'Concentrate', 'Opportunity'],
              bob=[(1, 'Wind Drake'), (1, 'Grizzly Bears'), (20, 'Island')])
    hold(s)
    source = put(s, NAME, 'battlefield')
    drake = put(s, 'Wind Drake', 'battlefield')
    enemy = put(s, 'Wind Drake', 'battlefield', 'p2')
    return s, source, drake, enemy


def pt(s, cards, target):
    from app.rules.sba import power, toughness

    c = s.state.cards[target.id]
    ch = Plan(s.state, c.controller, cards, None).ch(c)
    return power(c, ch), toughness(c, ch)


def cast_draw_one(s):
    spell = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Reach Through Mists' and not c.zone.endswith(':graveyard'))
    act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    for _ in range(12):
        if spell.id not in s.state.rules.stack:
            return
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('Draw spell did not resolve')


def to_four(s):
    while s.state.rules.draws_this_turn.get('p1', 0) < 4:
        cast_draw_one(s)
        settle(s)
    assert s.state.rules.draws_this_turn['p1'] == 4


def test_canonical_alandra_is_fully_supported(cards):
    c = coverage.of_card_data(cards.resolve(NAME))
    assert c.level == 'FULL', c.manual_parts


def test_fifth_draw_pumps_source_and_controlled_drakes_only_once_and_expires(cards):
    from tests.test_rules_wave34b_activated import to_phase

    s, source, drake, enemy = setup(cards)
    to_four(s)
    assert pt(s, cards, source) == (2, 4) and pt(s, cards, drake) == (2, 2)
    cast_draw_one(s)
    assert s.state.rules.draws_this_turn['p1'] == 5
    assert any(e.source_card == source.id and any(x.get('do') == 'pump' for x in e.effects) for e in s.state.rules.stack.values())
    n = len(s.state.zones['p1:hand'])
    roundtrip(s)
    settle(s)
    assert pt(s, cards, source) == (2 + n, 4 + n)
    assert pt(s, cards, drake) == (2 + n, 2 + n) and pt(s, cards, enemy) == (2, 2)
    cast_draw_one(s)
    settle(s)
    assert s.state.rules.draws_this_turn['p1'] == 6
    assert pt(s, cards, source) == (2 + n, 4 + n)
    to_phase(s, 'main1', turn=s.state.turn.number + 1)
    assert pt(s, cards, source) == (2, 4) and pt(s, cards, drake) == (2, 2)
    roundtrip(s)


def test_source_that_is_also_a_drake_is_not_pumped_twice(cards):
    s, source, drake, _ = setup(cards)
    put(s, 'Maskwood Nexus', 'battlefield')
    to_four(s)
    cast_draw_one(s)
    n = len(s.state.zones['p1:hand'])
    settle(s)
    assert pt(s, cards, source) == (2 + n, 4 + n)
    assert pt(s, cards, drake) == (2 + n, 2 + n)
    roundtrip(s)


def test_source_leaving_before_resolution_still_pumps_controlled_drakes(cards):
    s, source, drake, _ = setup(cards)
    to_four(s)
    cast_draw_one(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    n = len(s.state.zones['p1:hand'])
    settle(s)
    assert pt(s, cards, drake) == (2 + n, 2 + n)
    roundtrip(s)


def draw_three(s, player='p1'):
    spell = put(s, 'Ancestral Recall', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[player])
    for _ in range(12):
        if spell.id not in s.state.rules.stack:
            return
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('Recall did not resolve')


def test_multi_card_draw_crosses_fifth_exactly_once_and_reads_final_hand_on_resolution(cards):
    s, source, drake, _ = setup(cards)
    to_four(s)
    draw_three(s)
    assert s.state.rules.draws_this_turn['p1'] == 7
    triggers = [e for e in s.state.rules.stack.values() if e.source_card == source.id and any(x.get('do') == 'pump' for x in e.effects)]
    assert len(triggers) == 1
    n = len(s.state.zones['p1:hand'])
    roundtrip(s)
    settle(s)
    assert pt(s, cards, source) == (2 + n, 4 + n) and pt(s, cards, drake) == (2 + n, 2 + n)
    roundtrip(s)


def test_an_opponents_fifth_draw_does_not_trigger_alandra(cards):
    s, source, drake, _ = setup(cards)
    draw_three(s, 'p2')
    settle(s)
    draw_three(s, 'p2')
    settle(s)
    assert s.state.rules.draws_this_turn['p2'] == 6
    assert pt(s, cards, source) == (2, 4) and pt(s, cards, drake) == (2, 2)
    assert not any(c.is_token and c.name == 'Drake' for c in s.state.cards.values())
    roundtrip(s)


def test_pump_uses_hand_and_group_as_of_resolution_and_not_fifth_draw_time(cards):
    s, source, drake, _ = setup(cards)
    to_four(s)
    cast_draw_one(s)
    put(s, 'Grizzly Bears', 'hand')
    # A sixth draw resolves above the already pending fifth-draw trigger.
    cast_draw_one(s)
    n = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='set_controller', card_ids=[drake.id], player='p2')
    settle(s)
    assert pt(s, cards, source) == (2 + n, 4 + n) and pt(s, cards, drake) == (2, 2)
    roundtrip(s)


def test_pending_trigger_uses_original_controller_but_still_includes_source_after_control_change(cards):
    s, source, drake, enemy = setup(cards)
    to_four(s)
    cast_draw_one(s)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    n = len(s.state.zones['p1:hand'])
    settle(s)
    assert pt(s, cards, source) == (2 + n, 4 + n)
    assert pt(s, cards, drake) == (2 + n, 2 + n) and pt(s, cards, enemy) == (2, 2)
    roundtrip(s)


def test_blink_new_source_object_is_not_the_self_reference_but_drakes_still_get_pump(cards):
    s, source, drake, _ = setup(cards)
    to_four(s)
    cast_draw_one(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    n = len(s.state.zones['p1:hand'])
    settle(s)
    assert pt(s, cards, source) == (2, 4) and pt(s, cards, drake) == (2 + n, 2 + n)
    roundtrip(s)


@pytest.mark.parametrize('new_drake_first', [False, True])
def test_second_and_fifth_draw_triggers_from_one_spell_obey_controller_chosen_order(cards, new_drake_first):
    s, source, _, _ = setup(cards)
    cast_draw_one(s)
    settle(s)
    assert s.state.rules.draws_this_turn.get('p1') == 1
    spell = put(s, 'Opportunity', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'C': 4})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p1'])
    for _ in range(12):
        if spell.id not in s.state.rules.stack:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d and d.kind == 'order'
    pending = {t.id: t for t in s.state.rules.pending_triggers}
    pump = next(i for i in pending if any(e.get('do') == 'pump' for e in pending[i].ability['effects']))
    drake = next(i for i in pending if i != pump)
    n = len(s.state.zones['p1:hand'])
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[pump, drake] if new_drake_first else [drake, pump])
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.name == 'Drake']
    assert len(tokens) == 1
    assert pt(s, cards, tokens[0]) == ((2 + n, 2 + n) if new_drake_first else (2, 2))
    assert pt(s, cards, source) == (2 + n, 4 + n)
    roundtrip(s)


def test_new_source_object_can_qualify_independently_as_a_drake(cards):
    s, source, _, _ = setup(cards)
    put(s, 'Maskwood Nexus', 'battlefield')
    to_four(s)
    cast_draw_one(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    n = len(s.state.zones['p1:hand'])
    settle(s)
    assert pt(s, cards, source) == (2 + n, 4 + n)
    roundtrip(s)


def test_creatures_joining_controlled_drake_group_after_resolution_are_not_retroactively_pumped(cards):
    s, _, _, enemy = setup(cards)
    to_four(s)
    cast_draw_one(s)
    settle(s)
    act(s, 'p2', type='set_controller', card_ids=[enemy.id], player='p1')
    assert pt(s, cards, enemy) == (2, 2)
    roundtrip(s)
