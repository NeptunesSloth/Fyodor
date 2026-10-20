"""Abundance uses the native draw replacement order and never draws its found card."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/abundance_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def setup(cards):
    return table(cards, ['Abundance', 'Revitalize', 'Divination', 'Forest', 'Island', 'Lightning Bolt', 'Grizzly Bears', 'Sylvan Library', 'Prosperity'],
                 ['Notion Thief', 'Chromatic Sphere', 'Abundance', 'Narset, Parter of Veils'], ['Sylvan Library', 'Abundance'])


def set_library(s, names):
    for cid in list(s.state.zones['p1:library']):
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'graveyard'})
    result = []
    for name in names:
        c = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == name and c.id not in result)
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, position='bottom')
        result.append(c.id)
    return result


def begin(s):
    put(s, 'Abundance', 'battlefield')
    spell = put(s, 'Revitalize', 'hand')
    mana(s, C=1, W=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    return until_asked(s)


def test_abundance_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Abundance')).level == 'FULL'


@pytest.mark.parametrize('kind,names,index', [
    ('land', ['Lightning Bolt', 'Grizzly Bears', 'Forest', 'Island'], 2),
    ('nonland', ['Forest', 'Island', 'Lightning Bolt', 'Grizzly Bears', 'Sylvan Library', 'Prosperity'], 2),
    ('land', ['Forest', 'Island'], 0),
    ('nonland', ['Lightning Bolt', 'Forest'], 0),
])
def test_chosen_kind_reveals_until_match_and_puts_only_that_card_in_hand(cards, kind, names, index):
    s = setup(cards)
    top = set_library(s, names)
    drawn = s.state.rules.turn_log.drew.get('p1', 0)
    d = begin(s)
    assert d.player == 'p1' and 'decline' in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id != 'decline')])
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {'land', 'nonland'}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[kind])
    d = s.state.rules.decision
    if index > 1:
        assert d.kind == 'order' and d.player == 'p1'
        assert {o.id for o in d.options} == set(top[:index])
        assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
        assert all(s.view('p2')['cards'].get(cid, {}).get('name') for cid in top[:index])
        assert not s.view('p2')['cards'].get(top[index + 1], {}).get('name')
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=top[:index])
    settle(s)
    assert s.state.cards[top[index]].zone == 'p1:hand'
    assert s.state.zones['p1:library'] == top[index + 1:] + list(reversed(top[:index]))
    assert s.state.rules.turn_log.drew.get('p1', 0) == drawn
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p1:library'])
    assert not s.state.rules.lost
    roundtrip(s)


@pytest.mark.parametrize('names', [[], ['Lightning Bolt'], ['Lightning Bolt', 'Grizzly Bears']])
def test_absent_chosen_kind_puts_everything_on_bottom_without_drawing_or_losing(cards, names):
    s = setup(cards)
    top = set_library(s, names)
    drawn = s.state.rules.turn_log.drew.get('p1', 0)
    d = begin(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id != 'decline')])
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['land'])
    if len(top) > 1:
        d = s.state.rules.decision
        assert d.kind == 'order'
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=top)
    settle(s)
    assert s.state.zones['p1:library'] == list(reversed(top))
    assert all(s.state.cards[c].zone == 'p1:library' for c in top)
    assert s.state.rules.turn_log.drew.get('p1', 0) == drawn
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p1:library'])
    assert not s.state.rules.lost
    roundtrip(s)



@pytest.mark.parametrize('empty', [False, True])
def test_declining_replacement_performs_real_draw_or_empty_library_loss(cards, empty):
    s = setup(cards)
    top = set_library(s, [] if empty else ['Lightning Bolt'])
    drawn = s.state.rules.turn_log.drew.get('p1', 0)
    d = begin(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    if empty:
        assert 'p1' in s.state.rules.lost
    else:
        assert s.state.cards[top[0]].zone == 'p1:hand'
        assert s.state.rules.turn_log.drew.get('p1', 0) == drawn + 1
    roundtrip(s)


def test_multiple_draws_replace_separately_against_updated_library(cards):
    s = setup(cards)
    top = set_library(s, ['Forest', 'Lightning Bolt', 'Island', 'Grizzly Bears'])
    put(s, 'Abundance', 'battlefield')
    spell = put(s, 'Divination', 'hand')
    drawn = s.state.rules.turn_log.drew.get('p1', 0)
    mana(s, C=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    for kind in ['land', 'nonland']:
        d = until_asked(s)
        assert d.player == 'p1' and 'decline' in {o.id for o in d.options}
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id != 'decline')])
        d = s.state.rules.decision
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[kind])
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:hand' for c in top[:2])
    assert s.state.zones['p1:library'] == top[2:]
    assert s.state.rules.turn_log.drew.get('p1', 0) == drawn
    roundtrip(s)


@pytest.mark.parametrize('abundance_first', [False, True])
def test_affected_player_orders_abundance_and_notion_thief(cards, abundance_first):
    s = setup(cards)
    top = set_library(s, ['Forest', 'Lightning Bolt'])
    put(s, 'Notion Thief', 'battlefield', 'p2')
    before = len(s.state.zones['p2:hand'])
    d = begin(s)
    assert d.player == 'p1'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith('Abundance')) if abundance_first else 'decline'])
    if abundance_first:
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['land'])
    settle(s)
    assert len(s.state.zones['p2:hand']) == before + (0 if abundance_first else 1)
    assert s.state.cards[top[0]].zone == ('p1:hand' if abundance_first else 'p1:library')
    roundtrip(s)


def test_sylvan_library_cannot_charge_life_for_cards_put_into_hand_by_abundance(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, 'Abundance', 'battlefield')
    put(s, 'Sylvan Library', 'battlefield')
    # Reach the next upkeep first; it clears the current turn's drawn-card history.
    to_phase(s, 'upkeep', turn=4)
    top = set_library(s, ['Forest', 'Island', 'Lightning Bolt', 'Grizzly Bears'])
    life = s.state.players['p1'].life
    kinds = 0
    for _ in range(150):
        d = s.state.rules.decision
        if d is not None:
            if d.resume.get('step') == 'drawn_toll':
                assert d.options == [] and d.min_choices == d.max_choices == 0
                act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
                break
            if d.resume.get('step') == 'choose_land_nonland':
                ids = ['land' if kinds < 2 else 'nonland']
                kinds += 1
            elif 'yes' in {o.id for o in d.options}:
                ids = ['yes']
            else:
                ids = [next(o.id for o in d.options if o.id != 'decline')]
            act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    else:
        raise AssertionError('Sylvan Library never reached its drawn-card choice')
    settle(s)
    assert kinds == 3 and all(s.state.cards[c].zone == 'p1:hand' for c in top[:3])
    assert s.state.players['p1'].life == life
    assert s.state.rules.turn_log.drew.get('p1', 0) == 0
    roundtrip(s)



def test_each_players_draw_replacement_finishes_in_apnap_order(cards):
    s = setup(cards)
    for pid in ['p1', 'p2', 'p3']:
        put(s, 'Abundance', 'battlefield', pid)
        land = next(c for c in s.state.cards.values() if c.owner == pid and c.name == ('Forest' if pid == 'p1' else 'Island'))
        act(s, pid, type='move', card_ids=[land.id], to={'player': pid, 'zone': 'library'}, position='top')
    drawn = dict(s.state.rules.turn_log.drew)
    spell = put(s, 'Prosperity', 'hand')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=1)
    for pid in ['p1', 'p2', 'p3']:
        d = until_asked(s)
        assert d.player == pid and 'decline' in {o.id for o in d.options}
        act(s, pid, type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id != 'decline')])
        d = s.state.rules.decision
        assert d.player == pid and d.resume['step'] == 'choose_land_nonland'
        assert s.view('p2' if pid != 'p2' else 'p1')['rules']['decision']['kind'] == 'waiting'
        act(s, pid, type='choose', decision_id=d.id, option_ids=['land'])
    settle(s)
    assert dict(s.state.rules.turn_log.drew) == drawn
    roundtrip(s)



def test_draw_prohibition_does_not_offer_abundance_for_an_event_that_cannot_happen(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    to_phase(s, 'main1', turn=2)
    top = set_library(s, ['Forest', 'Island'])
    narset = put(s, 'Narset, Parter of Veils', 'hand', 'p2')
    mana(s, 'p2', C=1, U=2)
    act(s, 'p2', type='cast_spell', card_id=narset.id)
    settle(s)
    # The first draw is legal. Installing Abundance cannot replace a forbidden second draw.
    spell = put(s, 'Revitalize', 'hand')
    mana(s, C=1, W=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.rules.turn_log.drew.get('p1', 0) == 1
    assert s.state.cards[narset.id].zone == 'p2:battlefield'
    d = begin(s)
    assert d is None
    settle(s)
    assert s.state.zones['p1:library'] == top[1:]
    assert s.state.rules.turn_log.drew['p1'] == 1
    roundtrip(s)
