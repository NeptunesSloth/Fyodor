"""Exact exile-batch permissions and delayed remaining-card damage."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Wedding Ring'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/wedding_ring_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()






def setup(cards, defer=False, doubling=False):
    s = table(cards, [NAME, 'Disenchant', 'Ephemerate', 'Doubling Season', 'Crafty Cutpurse', 'Ghostly Flicker', 'Song of the Dryads', 'Forest', 'Revitalize'],
              ['Revitalize', 'Divination', 'Forest', 'Island', NAME])
    source = put(s, NAME, 'hand')
    if doubling:
        season = put(s, 'Doubling Season', 'battlefield')
        act(s, 'p1', type='set_controller', card_ids=[season.id], player='p2')
    mana(s, C=2, W=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'p2', 'p3'}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    if defer:
        return s, source, None
    settle(s)
    token = next(c for c in s.state.cards.values() if c.name == NAME and c.is_token)
    assert token.controller == token.owner == 'p2'
    assert len([c for c in s.state.cards.values() if c.name == NAME and c.zone.endswith(':battlefield')]) == (3 if doubling else 2)
    roundtrip(s)
    return s, source, token


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_actual_cast_creates_exactly_one_opponent_copy_without_recursive_etb(cards):
    setup(cards)


def test_own_turn_draw_and_life_gain_link_both_directions(cards):
    s, source, token = setup(cards)
    to_phase(s, 'main1', turn=2)
    settle(s)
    hand = len(s.state.zones['p1:hand'])
    spell = put(s, 'Revitalize', 'hand', 'p2')
    mana(s, C=1, W=1, pid='p2')
    act(s, 'p2', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.players['p1'].life == s.state.players['p2'].life == 43
    assert len(s.state.zones['p1:hand']) == hand + 1
    roundtrip(s)


def revitalize(s):
    spell = put(s, 'Revitalize', 'hand', 'p2')
    mana(s, C=1, W=1, pid='p2')
    if s.state.rules.priority != 'p2':
        act(s, s.state.rules.priority, type='pass_priority')
    act(s, 'p2', type='cast_spell', card_id=spell.id)
    settle(s)


def test_partner_drawing_or_gaining_outside_own_turn_does_not_trigger(cards):
    s, source, token = setup(cards)
    before = len(s.state.zones['p1:hand'])
    revitalize(s)
    assert s.state.players['p1'].life == 40 and s.state.players['p2'].life == 43
    assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)


def test_ring_name_without_artifact_type_does_not_qualify(cards):
    s, source, token = setup(cards)
    song = put(s, 'Song of the Dryads', 'hand')
    mana(s, C=2, G=1)
    act(s, 'p1', type='cast_spell', card_id=song.id, targets=[token.id])
    settle(s)
    to_phase(s, 'main1', turn=2)
    settle(s)
    before = len(s.state.zones['p1:hand'])
    revitalize(s)
    assert s.state.players['p1'].life == 40
    assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)


def test_real_blink_does_not_create_another_copy_when_not_cast(cards):
    s, source, token = setup(cards)
    forest = put(s, 'Forest', 'battlefield')
    blink = put(s, 'Ghostly Flicker', 'hand')
    mana(s, C=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[source.id, forest.id], target_counts=[2])
    settle(s)
    assert len([c for c in s.state.cards.values() if c.name == NAME and c.zone.endswith(':battlefield')]) == 2
    assert s.state.rules.decision is None
    roundtrip(s)


def test_partner_control_checked_on_event_not_again_when_trigger_resolves(cards):
    s, source, token = setup(cards)
    to_phase(s, 'main1', turn=2)
    settle(s)
    before = len(s.state.zones['p1:hand'])
    div = put(s, 'Divination', 'hand', 'p2')
    mana(s, C=2, U=1, pid='p2')
    act(s, 'p2', type='cast_spell', card_id=div.id)
    for _ in range(20):
        if s.state.cards[div.id].zone != 'stack':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    spell = put(s, 'Disenchant', 'hand')
    mana(s, C=1, W=1)
    while s.state.rules.priority != 'p1':
        act(s, s.state.rules.priority, type='pass_priority')
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[token.id])
    settle(s)
    assert token.id not in s.state.cards or s.state.cards[token.id].zone != 'p2:battlefield'
    assert len(s.state.zones['p1:hand']) == before + 2 - 1
    roundtrip(s)


def test_source_leaves_in_response_copy_uses_battlefield_lki(cards):
    s, source, _ = setup(cards, defer=True)
    spell = put(s, 'Disenchant', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    copies = [c for c in s.state.cards.values() if c.name == NAME and c.is_token and c.zone.endswith(':battlefield')]
    assert len(copies) == 1 and copies[0].controller == 'p2'
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_target_opponents_token_doubler_applies(cards):
    s, source, token = setup(cards, doubling=True)
    assert len([c for c in s.state.cards.values() if c.name == NAME and c.is_token and c.controller == 'p2']) == 2
    to_phase(s, 'main1', turn=2)
    settle(s)
    before = len(s.state.zones['p1:hand'])
    revitalize(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    assert s.state.players['p1'].life == 43
    roundtrip(s)


def test_actual_cutpurse_changes_creator_for_target_opponent_copy(cards):
    s, source, _ = setup(cards, defer=True)
    thief = put(s, 'Crafty Cutpurse', 'hand')
    mana(s, C=3, U=1)
    act(s, 'p1', type='cast_spell', card_id=thief.id)
    settle(s)
    copies = [c for c in s.state.cards.values() if c.name == NAME and c.is_token]
    assert len(copies) == 1 and copies[0].owner == copies[0].controller == 'p1'
    roundtrip(s)


def test_token_ring_reciprocates_on_original_controllers_turn_without_loops(cards):
    s, source, token = setup(cards)
    before = len(s.state.zones['p2:hand'])
    spell = put(s, 'Revitalize', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert s.state.players['p1'].life == s.state.players['p2'].life == 43
    assert len(s.state.zones['p2:hand']) == before + 1
    roundtrip(s)
