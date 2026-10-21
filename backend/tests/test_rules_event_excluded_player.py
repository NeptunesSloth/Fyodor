"""Player targets excluding the player named by a cast event."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/event_excluded_player_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'The Lord of Pain'


def setup(cards):
    return table(cards, [NAME, 'Lightning Bolt', 'Counterspell', 'Blaze', 'Ornithopter', 'Stifle', 'Leyline of Sanctity', 'Revitalize', 'Strionic Resonator'],
                 ['Lightning Bolt', 'Blaze', 'Ornithopter', 'Counterspell', 'Revitalize'], ['Lightning Bolt', 'Leyline of Sanctity'])


def test_lord_of_pain_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('caster', ['p1', 'p2'])
def test_another_player_excludes_caster_not_ability_controller(cards, caster):
    s = setup(cards)
    put(s, NAME, 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'hand', caster)
    wait_priority(s, caster)
    mana(s, caster, R=1)
    act(s, caster, type='cast_spell', card_id=bolt.id, targets=['p3'])
    d = until_asked(s)
    assert d.player == 'p1' and {o.id for o in d.options} == ({'p1', 'p2', 'p3'} - {caster})
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[caster])
    roundtrip(s)
    target = 'p1' if caster == 'p2' else 'p2'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target])
    settle(s)
    assert s.state.players[target].life == 39 and s.state.players['p3'].life == 37
    roundtrip(s)


def test_zero_mana_value_spell_damages_zero(cards):
    s = setup(cards)
    put(s, NAME, 'battlefield')
    spell = put(s, 'Ornithopter', 'hand')
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    d = until_asked(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    settle(s)
    assert all(p.life == 40 for p in s.state.players.values())
    roundtrip(s)


@pytest.mark.parametrize('counter_original', [False, True])
def test_spell_mana_value_includes_x_even_after_leaving_stack(cards, counter_original):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'main1', turn=2)
    blaze = put(s, 'Blaze', 'hand', 'p2')
    act(s, 'p2', type='set_prefs', hold_priority=True)
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1, C=4)
    act(s, 'p2', type='cast_spell', card_id=blaze.id, x_value=4, targets=['p3'])
    d = until_asked(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p1'])
    if counter_original:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
        wait_priority(s, 'p1')
        counter = put(s, 'Counterspell', 'hand')
        mana(s, U=2)
        act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[blaze.id])
    settle(s)
    assert s.state.players['p1'].life == 35
    assert s.state.players['p3'].life == (40 if counter_original else 36)
    roundtrip(s)


def test_first_spell_count_includes_spells_before_lord_entered(cards):
    s = setup(cards)
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    settle(s)
    put(s, NAME, 'battlefield')
    act(s, 'p1', type='move', card_ids=[bolt.id], to={'player': 'p2', 'zone': 'hand'})
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    settle(s)
    assert s.state.rules.decision is None and s.state.players['p3'].life == 34
    assert s.state.players['p1'].life == 40
    roundtrip(s)



def test_each_player_has_a_first_spell_each_turn_and_later_spells_do_not_trigger(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, NAME, 'battlefield')
    for caster in ['p1', 'p2', 'p3']:
        bolt = put(s, 'Lightning Bolt', 'hand', caster)
        for number in range(2):
            if number:
                act(s, 'p1', type='move', card_ids=[bolt.id], to={'player': caster, 'zone': 'hand'})
            wait_priority(s, caster)
            mana(s, caster, R=1)
            act(s, caster, type='cast_spell', card_id=bolt.id, targets=['p3'])
            if not number:
                d = until_asked(s)
                assert d.player == 'p1' and caster not in {o.id for o in d.options}
                act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2' if caster == 'p1' else 'p1'])
            else:
                assert s.state.rules.decision is None
            settle(s)
    to_phase(s, 'main1', turn=2)
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    d = until_asked(s)
    assert d.player == 'p1' and 'p2' not in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p1'])
    settle(s)
    roundtrip(s)


def test_player_hexproof_rechecks_target_with_bound_caster_exclusion(cards):
    s = setup(cards)
    put(s, NAME, 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p1'])
    d = until_asked(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    put(s, 'Leyline of Sanctity', 'battlefield', 'p3')
    settle(s)
    assert s.state.players['p3'].life == 40 and s.state.players['p1'].life == 37
    roundtrip(s)


def test_lord_existing_life_prohibition_applies_to_opponents_only(cards):
    s = setup(cards)
    put(s, NAME, 'battlefield')
    for caster, target in [('p2', 'p1'), ('p1', 'p2')]:
        spell = put(s, 'Revitalize', 'hand', caster)
        wait_priority(s, caster)
        mana(s, caster, W=1, C=1)
        act(s, caster, type='cast_spell', card_id=spell.id)
        d = until_asked(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target])
        settle(s)
    assert s.state.players['p1'].life == 41 and s.state.players['p2'].life == 38
    roundtrip(s)


def test_copied_trigger_keeps_original_caster_exclusion_after_source_control_changes(cards):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    resonator = put(s, 'Strionic Resonator', 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    d = until_asked(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p1'])
    trigger = next(cid for cid, e in s.state.rules.stack.items() if e.kind == 'trigger')
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    wait_priority(s, 'p1')
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=resonator.id, ability=0, targets=[trigger])
    d = until_asked(s)
    assert d.player == 'p1' and d.resume['step'] == 'copy_target'
    assert 'p2' not in {o.id for o in d.options} and 'p3' in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    settle(s)
    assert s.state.players['p1'].life == 39 and s.state.players['p3'].life == 36
    roundtrip(s)
